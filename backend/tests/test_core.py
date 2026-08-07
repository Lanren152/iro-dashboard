import os
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite:///./test_investment_os.db"
os.environ["AUTO_SEED"] = "false"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import (
    Company,
    CompanySnapshot,
    Evidence,
    MetricObservation,
    Opportunity,
    ProfitDriver,
    ResearchReport,
    Sector,
)
from app.seed import seed_all
from app.schemas import FinancialScenarioInput
from app.services.anomaly import detect_anomaly
from app.services.expectation import reverse_implied_growth
from app.services.financial import run_financial_scenario


def setup_module():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    result = seed_all()
    assert result["sectors"] == 40
    assert result["companies"] >= 70
    assert result["company_snapshots"] >= 500


def test_financial_scenario_and_reverse_expectation():
    result = run_financial_scenario(FinancialScenarioInput(
        volume=10,
        price=20,
        unit_cost=12,
        fixed_cost=10,
        tax_rate=.25,
        shares=5,
        valuation_multiple=20,
    ))
    assert result["net_profit"] == 52.5
    assert result["implied_value_per_share"] == 210.0
    implied = reverse_implied_growth(price=20, current_eps=1, exit_pe=20, years=3, required_return=.15)
    assert .14 < implied < .16


def test_anomaly_requires_persistence():
    result = detect_anomaly("x", [100, 101, 100, 102, 104, 108, 114, 124], 1)
    assert result.triggered
    assert result.persistence >= 2 / 3
    noisy = detect_anomaly("x", [100, 101, 100, 102, 120, 100, 122, 121], 1)
    assert not noisy.triggered


def test_full_cycle_is_repeatable_and_audited():
    with TestClient(app) as client:
        first = client.post("/api/research/run-cycle")
        second = client.post("/api/research/run-cycle")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["processed_count"] >= 5
        assert second.json()["processed_count"] == first.json()["processed_count"]
        assert second.json()["failed_count"] == 0

        dashboard = client.get("/api/dashboard").json()
        assert dashboard["counts"]["sectors"] == 40
        assert dashboard["counts"]["companies"] >= 70
        assert dashboard["counts"]["company_snapshots"] >= 500
        assert dashboard["counts"]["evidence"] > 0
        assert dashboard["recent_reports"]

        opportunities = client.get("/api/opportunities?limit=100").json()
        assert {x["origin"] for x in opportunities} >= {"market", "company"}
        assert all(x["stage"] == "deep_research" for x in opportunities)


def test_company_research_surface_and_versioned_model():
    with TestClient(app) as client:
        company = client.get("/api/companies?limit=1").json()[0]
        detail = client.get(f"/api/companies/{company['id']}")
        assert detail.status_code == 200
        data = detail.json()
        assert data["profit_tree"]
        assert set(data["financial_model"]["scenarios"]) == {"bear", "base", "bull"}
        assert data["market_expectations"]

        first = client.post(f"/api/companies/{company['id']}/assumptions", json={
            "variable": "volume",
            "scenario": "base",
            "period": "2027",
            "value": 100,
            "rationale": "first revision",
            "evidence_ids": [],
        }).json()
        second = client.post(f"/api/companies/{company['id']}/assumptions", json={
            "variable": "volume",
            "scenario": "base",
            "period": "2027",
            "value": 110,
            "rationale": "second revision",
            "evidence_ids": [],
        }).json()
        assert first["revision"] == 1
        assert second["revision"] == 2


def test_opportunity_detail_contains_required_audit_data():
    with TestClient(app) as client:
        opportunity = client.get("/api/opportunities?limit=1").json()[0]
        detail = client.get(f"/api/opportunities/{opportunity['id']}")
        assert detail.status_code == 200
        data = detail.json()
        assert data["candidate_companies"]
        assert data["evidence"]
        assert data["transitions"]
        assert data["tasks"]
        assert data["predictions"]


def test_real_metric_signals_are_not_forced_to_demo():
    with SessionLocal() as session:
        sector = session.get(Sector, "01")
        assert sector
        now = datetime(2026, 8, 1, tzinfo=timezone.utc)
        for metric_suffix in ("demand_index", "order_growth"):
            code = f"01_{metric_suffix}"
            for source_idx, source_name in enumerate(("official statistics", "licensed industry")):
                for i, value in enumerate([100, 100, 101, 102, 105, 110, 118, 130]):
                    session.add(MetricObservation(
                        metric_code=code,
                        period=now - timedelta(days=30 * (7 - i)),
                        value=value + source_idx * .2,
                        source_name=source_name,
                        source_url="https://example.invalid/source",
                        credibility=.95,
                        is_demo=False,
                    ))
        session.commit()

    with TestClient(app) as client:
        response = client.post("/api/research/run-scan")
        assert response.status_code == 200
        item = next(x for x in response.json()["items"] if x["sector_code"] == "01")
        assert item["is_demo"] is False

    with SessionLocal() as session:
        opportunity = session.exec(select(Opportunity).where(
            Opportunity.sector_code == "01",
            Opportunity.origin == "market",
        )).first()
        assert opportunity and not opportunity.is_demo
        verified = session.exec(select(Evidence).where(
            Evidence.sector_code == "01",
            Evidence.verified.is_(True),
        )).all()
        assert len(verified) >= 4


def test_persistence_tables_created():
    with SessionLocal() as session:
        assert session.exec(select(Company)).first()
        assert session.exec(select(CompanySnapshot)).first()
        assert session.exec(select(ProfitDriver)).first()
        assert session.exec(select(ResearchReport)).first()
