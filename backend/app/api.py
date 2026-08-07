import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select

from .db import AppSession as Session
from .db import get_session
from .models import (
    AgentRun,
    Company,
    CompanySectorMembership,
    CompanySnapshot,
    Evidence,
    MarketExpectation,
    MetricDefinition,
    MetricObservation,
    Opportunity,
    OpportunityCompany,
    PredictionSnapshot,
    ProfitAssumption,
    ResearchReport,
    ResearchTask,
    Sector,
    SourceDocument,
    StateTransition,
    SystemAlert,
)
from .schemas import (
    CompanyMembershipInput,
    CompanySnapshotInput,
    DocumentInput,
    FinancialScenarioInput,
    HypothesisInput,
    MetricInput,
    PredictionEvaluationInput,
    ProfitAssumptionInput,
    ReverseExpectationInput,
    StateChangeInput,
)
from .services.company_analysis import CompanyAnalysisService
from .services.evaluation import EvaluationService
from .services.evidence import EvidenceService
from .services.expectation import ExpectationService, reverse_implied_growth
from .services.financial import FinancialModelService, run_financial_scenario
from .services.monitoring import MonitoringService
from .services.profit_tree import ProfitTreeService
from .services.radar import MarketRadar
from .services.reporting import ReportingService
from .services.state_machine import validate_transition
from .agents.orchestrator import ResearchOrchestrator

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc)}


@router.get("/dashboard")
def dashboard(session: Session = Depends(get_session)):
    opportunities = session.exec(select(Opportunity).order_by(Opportunity.score.desc())).all()
    tasks = session.exec(select(ResearchTask).order_by(ResearchTask.created_at.desc()).limit(10)).all()
    runs = session.exec(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(10)).all()
    alerts = session.exec(select(SystemAlert).where(SystemAlert.status == "open").order_by(SystemAlert.created_at.desc()).limit(10)).all()
    reports = session.exec(select(ResearchReport).order_by(ResearchReport.created_at.desc()).limit(3)).all()
    return {
        "counts": {
            "sectors": len(session.exec(select(Sector)).all()),
            "companies": len(session.exec(select(Company)).all()),
            "company_snapshots": len(session.exec(select(CompanySnapshot)).all()),
            "opportunities": len(opportunities),
            "evidence": len(session.exec(select(Evidence)).all()),
            "verified_evidence": len(session.exec(select(Evidence).where(Evidence.verified.is_(True))).all()),
            "metric_observations": len(session.exec(select(MetricObservation)).all()),
            "open_alerts": len(session.exec(select(SystemAlert).where(SystemAlert.status == "open")).all()),
        },
        "stage_counts": {
            stage: sum(1 for x in opportunities if x.stage == stage)
            for stage in sorted(set(x.stage for x in opportunities))
        },
        "top_opportunities": opportunities[:12],
        "recent_tasks": tasks,
        "recent_runs": runs,
        "open_alerts": alerts,
        "recent_reports": reports,
        "demo_notice": "DEMO records are synthetic and not investment facts",
    }


@router.get("/sectors")
def sectors(session: Session = Depends(get_session)):
    return session.exec(select(Sector).order_by(Sector.code)).all()


@router.get("/sectors/{sector_code}")
def sector_detail(sector_code: str, session: Session = Depends(get_session)):
    sector = session.get(Sector, sector_code)
    if not sector:
        raise HTTPException(404, "Sector not found")
    metrics = session.exec(select(MetricDefinition).where(MetricDefinition.sector_code == sector_code)).all()
    memberships = session.exec(select(CompanySectorMembership).where(CompanySectorMembership.sector_code == sector_code)).all()
    companies = [session.get(Company, x.company_id) for x in memberships]
    if not companies:
        companies = session.exec(select(Company).where(Company.sector_code == sector_code)).all()
    opportunities = session.exec(select(Opportunity).where(
        Opportunity.sector_code == sector_code
    ).order_by(Opportunity.score.desc())).all()
    evidence = session.exec(select(Evidence).where(
        Evidence.sector_code == sector_code
    ).order_by(Evidence.created_at.desc()).limit(100)).all()
    return {
        "sector": sector,
        "metrics": metrics,
        "companies": companies,
        "opportunities": opportunities,
        "evidence": evidence,
    }


@router.get("/companies")
def companies(
    sector_code: str | None = None,
    q: str | None = None,
    limit: int = Query(100, le=1000),
    session: Session = Depends(get_session),
):
    stmt = select(Company)
    if sector_code:
        member_ids = [x.company_id for x in session.exec(select(CompanySectorMembership).where(
            CompanySectorMembership.sector_code == sector_code
        )).all()]
        stmt = stmt.where(or_(Company.sector_code == sector_code, Company.id.in_(member_ids or [-1])))
    if q:
        stmt = stmt.where(or_(Company.name.contains(q), Company.ticker.contains(q)))
    return session.exec(stmt.order_by(Company.market_cap.desc()).limit(limit)).all()


@router.get("/companies/{company_id}")
def company_detail(company_id: int, session: Session = Depends(get_session)):
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    snapshots = session.exec(select(CompanySnapshot).where(
        CompanySnapshot.company_id == company_id
    ).order_by(CompanySnapshot.period.desc()).limit(20)).all()
    memberships = session.exec(select(CompanySectorMembership).where(
        CompanySectorMembership.company_id == company_id
    )).all()
    evidence = session.exec(select(Evidence).where(
        Evidence.company_id == company_id
    ).order_by(Evidence.created_at.desc())).all()
    assumptions = session.exec(select(ProfitAssumption).where(
        ProfitAssumption.company_id == company_id
    ).order_by(ProfitAssumption.created_at.desc())).all()
    expectations = session.exec(select(MarketExpectation).where(
        MarketExpectation.company_id == company_id
    ).order_by(MarketExpectation.as_of.desc())).all()
    return {
        "company": company,
        "memberships": memberships,
        "snapshots": snapshots,
        "profit_tree": ProfitTreeService(session).as_tree(company_id),
        "financial_model": FinancialModelService(session).run_company(company_id),
        "market_expectations": expectations,
        "evidence": evidence,
        "assumptions": assumptions,
    }


@router.get("/companies/{company_id}/peers")
def compare_peers(company_id: int, session: Session = Depends(get_session)):
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    memberships = session.exec(select(CompanySectorMembership).where(
        CompanySectorMembership.company_id == company_id
    )).all()
    sector_codes = {company.sector_code, *(x.sector_code for x in memberships)}
    peer_ids = set()
    for sector_code in sector_codes:
        peer_ids.update(x.company_id for x in session.exec(select(CompanySectorMembership).where(
            CompanySectorMembership.sector_code == sector_code
        )).all())
    if not peer_ids:
        peer_ids.update(x.id for x in session.exec(select(Company).where(Company.sector_code == company.sector_code)).all())
    service = CompanyAnalysisService(session)
    rows = []
    for peer_id in peer_ids:
        peer = session.get(Company, peer_id)
        snapshot = service.latest_snapshot(peer_id)
        rows.append({"company": peer, "snapshot": snapshot})
    rows.sort(key=lambda x: (x["snapshot"].profit_growth if x["snapshot"] and x["snapshot"].profit_growth is not None else -999), reverse=True)
    return rows


@router.get("/companies/{company_id}/profit-tree")
def profit_tree(company_id: int, session: Session = Depends(get_session)):
    if not session.get(Company, company_id):
        raise HTTPException(404, "Company not found")
    return ProfitTreeService(session).as_tree(company_id)


@router.post("/companies/{company_id}/assumptions")
def add_profit_assumption(company_id: int, x: ProfitAssumptionInput, session: Session = Depends(get_session)):
    if not session.get(Company, company_id):
        raise HTTPException(404, "Company not found")
    return FinancialModelService(session).add_assumption(
        company_id=company_id,
        variable=x.variable,
        scenario=x.scenario,
        period=x.period,
        value=x.value,
        unit=x.unit,
        rationale=x.rationale,
        evidence_ids=x.evidence_ids,
        opportunity_id=x.opportunity_id,
    )


@router.get("/companies/{company_id}/financial-model")
def company_financial_model(company_id: int, period: str = "next_year", session: Session = Depends(get_session)):
    if not session.get(Company, company_id):
        raise HTTPException(404, "Company not found")
    return FinancialModelService(session).run_company(company_id, period)


@router.get("/opportunities")
def opportunities(
    stage: str | None = None,
    origin: str | None = None,
    limit: int = Query(100, le=500),
    session: Session = Depends(get_session),
):
    stmt = select(Opportunity)
    if stage:
        stmt = stmt.where(Opportunity.stage == stage)
    if origin:
        stmt = stmt.where(Opportunity.origin == origin)
    return session.exec(stmt.order_by(Opportunity.score.desc()).limit(limit)).all()


@router.get("/opportunities/{opportunity_id}")
def opportunity_detail(opportunity_id: int, session: Session = Depends(get_session)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        raise HTTPException(404, "Opportunity not found")
    links = session.exec(select(OpportunityCompany).where(
        OpportunityCompany.opportunity_id == opportunity_id
    ).order_by(OpportunityCompany.ranking_score.desc())).all()
    candidates = []
    for link in links:
        company = session.get(Company, link.company_id)
        expectation = session.exec(select(MarketExpectation).where(
            MarketExpectation.company_id == link.company_id
        ).order_by(MarketExpectation.as_of.desc())).first()
        candidates.append({
            "link": link,
            "company": company,
            "market_expectation": expectation,
        })
    evidence = session.exec(select(Evidence).where(
        Evidence.sector_code == opportunity.sector_code
    ).order_by(Evidence.created_at.desc())).all()
    transitions = session.exec(select(StateTransition).where(
        StateTransition.opportunity_id == opportunity_id
    ).order_by(StateTransition.created_at)).all()
    tasks = session.exec(select(ResearchTask).where(
        ResearchTask.subject_type == "opportunity",
        ResearchTask.subject_id == str(opportunity_id),
    ).order_by(ResearchTask.created_at.desc()).limit(10)).all()
    predictions = session.exec(select(PredictionSnapshot).where(
        PredictionSnapshot.opportunity_id == opportunity_id
    ).order_by(PredictionSnapshot.as_of.desc())).all()
    return {
        "opportunity": opportunity,
        "candidate_companies": candidates,
        "evidence": evidence,
        "transitions": transitions,
        "tasks": tasks,
        "predictions": predictions,
    }


@router.post("/hypotheses")
def create_hypothesis(x: HypothesisInput, session: Session = Depends(get_session)):
    if not session.get(Sector, x.sector_code):
        raise HTTPException(400, "Unknown sector code")
    opportunity = Opportunity(
        title=x.title,
        sector_code=x.sector_code,
        origin="company" if x.origin_company_id else "manual",
        origin_company_id=x.origin_company_id,
        stage="watch",
        thesis=x.thesis,
        missing_evidence="; ".join(x.missing_evidence),
        falsification_conditions="; ".join(x.falsification_conditions),
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)
    return opportunity


@router.post("/opportunities/{opportunity_id}/state")
def change_state(opportunity_id: int, x: StateChangeInput, session: Session = Depends(get_session)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        raise HTTPException(404, "Opportunity not found")
    try:
        validate_transition(opportunity.stage, x.stage)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    old = opportunity.stage
    opportunity.stage = x.stage
    opportunity.updated_at = datetime.now(timezone.utc)
    session.add(StateTransition(
        opportunity_id=opportunity.id,
        from_stage=old,
        to_stage=x.stage,
        reason=x.reason,
        actor=x.actor,
    ))
    session.add(opportunity)
    session.commit()
    return opportunity


@router.get("/evidence")
def search_evidence(
    q: str | None = None,
    sector_code: str | None = None,
    company_id: int | None = None,
    verified: bool | None = None,
    limit: int = Query(100, le=1000),
    session: Session = Depends(get_session),
):
    stmt = select(Evidence)
    if q:
        stmt = stmt.where(or_(Evidence.claim.contains(q), Evidence.variable.contains(q)))
    if sector_code:
        stmt = stmt.where(Evidence.sector_code == sector_code)
    if company_id is not None:
        stmt = stmt.where(Evidence.company_id == company_id)
    if verified is not None:
        stmt = stmt.where(Evidence.verified == verified)
    return session.exec(stmt.order_by(Evidence.created_at.desc()).limit(limit)).all()


@router.get("/documents")
def search_documents(
    q: str | None = None,
    source_type: str | None = None,
    sector_code: str | None = None,
    company_id: int | None = None,
    limit: int = Query(100, le=500),
    session: Session = Depends(get_session),
):
    stmt = select(SourceDocument)
    if q:
        stmt = stmt.where(or_(SourceDocument.title.contains(q), SourceDocument.parsed_text.contains(q)))
    if source_type:
        stmt = stmt.where(SourceDocument.source_type == source_type)
    if sector_code:
        stmt = stmt.where(SourceDocument.sector_code == sector_code)
    if company_id is not None:
        stmt = stmt.where(SourceDocument.company_id == company_id)
    return session.exec(stmt.order_by(SourceDocument.published_at.desc()).limit(limit)).all()


@router.get("/documents/{document_id}")
def read_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(SourceDocument, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    evidence = session.exec(select(Evidence).where(Evidence.source_document_id == document_id)).all()
    return {"document": document, "evidence": evidence}


@router.get("/alerts")
def alerts(status: str = "open", limit: int = Query(100, le=500), session: Session = Depends(get_session)):
    stmt = select(SystemAlert)
    if status:
        stmt = stmt.where(SystemAlert.status == status)
    return session.exec(stmt.order_by(SystemAlert.created_at.desc()).limit(limit)).all()


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, session: Session = Depends(get_session)):
    alert = session.get(SystemAlert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.status = "resolved"
    alert.resolved_at = datetime.now(timezone.utc)
    session.add(alert)
    session.commit()
    return alert


@router.get("/reports")
def reports(cadence: str | None = None, limit: int = Query(20, le=100), session: Session = Depends(get_session)):
    stmt = select(ResearchReport)
    if cadence:
        stmt = stmt.where(ResearchReport.cadence == cadence)
    items = session.exec(stmt.order_by(ResearchReport.created_at.desc()).limit(limit)).all()
    return [{
        "id": x.id,
        "cadence": x.cadence,
        "period_start": x.period_start,
        "period_end": x.period_end,
        "title": x.title,
        "summary": json.loads(x.summary_json),
        "created_at": x.created_at,
    } for x in items]


@router.post("/reports/generate")
def generate_report(cadence: str = "daily", session: Session = Depends(get_session)):
    report = ReportingService(session).generate(cadence)
    return {"report": report, "summary": json.loads(report.summary_json)}


@router.post("/research/run-scan")
def run_scan(session: Session = Depends(get_session)):
    return {"items": MarketRadar(session).scan()}


@router.post("/research/run-cycle")
def run_cycle(session: Session = Depends(get_session)):
    return ResearchOrchestrator(session).run_cycle()


@router.post("/research/run-monitoring")
def run_monitoring(session: Session = Depends(get_session)):
    return MonitoringService(session).review_all()


@router.post("/financial/scenario")
def financial_scenario(x: FinancialScenarioInput):
    return run_financial_scenario(x)


@router.post("/financial/reverse-expectation")
def reverse_expectation(x: ReverseExpectationInput):
    return {
        "implied_eps_growth": reverse_implied_growth(
            x.price, x.current_eps, x.exit_pe, x.years, x.required_return
        ),
        "assumptions": x.model_dump(),
    }


@router.post("/predictions/{snapshot_id}/evaluate")
def evaluate_prediction(snapshot_id: int, x: PredictionEvaluationInput, session: Session = Depends(get_session)):
    try:
        return EvaluationService(session).evaluate_score(snapshot_id, x.actual_value)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/ingest/document")
def ingest_document(x: DocumentInput, session: Session = Depends(get_session)):
    digest = hashlib.sha256(x.parsed_text.encode()).hexdigest()
    existing = session.exec(select(SourceDocument).where(SourceDocument.content_hash == digest)).first()
    if existing:
        return existing
    company_id = None
    if x.company_ticker:
        company = session.exec(select(Company).where(Company.ticker == x.company_ticker)).first()
        if not company:
            raise HTTPException(400, "Unknown company ticker")
        company_id = company.id
    payload = x.model_dump(exclude={"company_ticker"}) | {"content_hash": digest, "company_id": company_id}
    document = SourceDocument(**payload)
    session.add(document)
    session.commit()
    session.refresh(document)
    EvidenceService(session).extract_documents()
    return document


@router.post("/ingest/metric")
def ingest_metric(x: MetricInput, session: Session = Depends(get_session)):
    if not session.exec(select(MetricDefinition).where(MetricDefinition.code == x.metric_code)).first():
        raise HTTPException(400, "Unknown metric code")
    observation = MetricObservation(**x.model_dump())
    session.add(observation)
    session.commit()
    session.refresh(observation)
    return observation


@router.post("/ingest/company-membership")
def ingest_company_membership(x: CompanyMembershipInput, session: Session = Depends(get_session)):
    company = session.exec(select(Company).where(Company.ticker == x.ticker)).first()
    if not company:
        raise HTTPException(400, "Unknown company ticker")
    if not session.get(Sector, x.sector_code):
        raise HTTPException(400, "Unknown sector code")
    existing = session.exec(select(CompanySectorMembership).where(
        CompanySectorMembership.company_id == company.id,
        CompanySectorMembership.sector_code == x.sector_code,
        CompanySectorMembership.relationship_type == x.relationship_type,
    )).first()
    payload = x.model_dump(exclude={"ticker"}) | {"company_id": company.id}
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        membership = existing
    else:
        membership = CompanySectorMembership(**payload)
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return membership


@router.post("/ingest/company-snapshot")
def ingest_company_snapshot(x: CompanySnapshotInput, session: Session = Depends(get_session)):
    company = session.exec(select(Company).where(Company.ticker == x.ticker)).first()
    if not company:
        raise HTTPException(400, "Unknown company ticker")
    payload = x.model_dump(exclude={"ticker"}) | {"company_id": company.id}
    snapshot = CompanySnapshot(**payload)
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    ExpectationService(session).refresh_company(company.id)
    return snapshot
