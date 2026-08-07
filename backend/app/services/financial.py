from collections import defaultdict
from sqlalchemy import func, select

from ..db import AppSession as Session
from ..models import CompanySnapshot, ProfitAssumption
from ..schemas import FinancialScenarioInput


def run_financial_scenario(x: FinancialScenarioInput) -> dict:
    revenue = x.volume * x.price
    gross_profit = x.volume * (x.price - x.unit_cost)
    pre_tax = gross_profit - x.fixed_cost
    tax = max(0.0, pre_tax * x.tax_rate)
    net_profit = pre_tax - tax
    eps = net_profit / x.shares
    implied_value = eps * x.valuation_multiple
    margin = net_profit / revenue if revenue else 0.0
    return {
        "revenue": round(revenue, 4),
        "gross_profit": round(gross_profit, 4),
        "pre_tax_profit": round(pre_tax, 4),
        "net_profit": round(net_profit, 4),
        "net_margin": round(margin, 6),
        "eps": round(eps, 6),
        "implied_value_per_share": round(implied_value, 4),
        "assumptions": x.model_dump(),
    }


class FinancialModelService:
    REQUIRED = ("volume", "price", "unit_cost", "fixed_cost", "tax_rate", "shares", "valuation_multiple")

    def __init__(self, session: Session):
        self.session = session

    def add_assumption(
        self,
        company_id: int,
        variable: str,
        scenario: str,
        period: str,
        value: float,
        unit: str = "",
        rationale: str = "",
        evidence_ids: list[int] | None = None,
        opportunity_id: int | None = None,
    ) -> ProfitAssumption:
        latest_revision = self.session.exec(select(func.max(ProfitAssumption.revision)).where(
            ProfitAssumption.company_id == company_id,
            ProfitAssumption.variable == variable,
            ProfitAssumption.scenario == scenario,
            ProfitAssumption.period == period,
        )).first() or 0
        item = ProfitAssumption(
            company_id=company_id,
            opportunity_id=opportunity_id,
            variable=variable,
            scenario=scenario,
            period=period,
            value=value,
            unit=unit,
            rationale=rationale,
            evidence_ids=",".join(str(x) for x in (evidence_ids or [])),
            revision=int(latest_revision) + 1,
        )
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def latest_assumptions(self, company_id: int, period: str) -> dict[str, dict[str, ProfitAssumption]]:
        items = self.session.exec(select(ProfitAssumption).where(
            ProfitAssumption.company_id == company_id,
            ProfitAssumption.period == period,
        ).order_by(ProfitAssumption.revision)).all()
        latest: dict[str, dict[str, ProfitAssumption]] = defaultdict(dict)
        for item in items:
            latest[item.scenario][item.variable] = item
        return latest

    def ensure_from_snapshot(self, company_id: int, period: str = "next_year") -> None:
        if self.latest_assumptions(company_id, period):
            return
        snapshot = self.session.exec(select(CompanySnapshot).where(
            CompanySnapshot.company_id == company_id,
            CompanySnapshot.data_kind.in_(["financial", "composite"]),
        ).order_by(CompanySnapshot.period.desc(), CompanySnapshot.version_key.desc())).first()
        if not snapshot or not snapshot.revenue or not snapshot.net_profit or not snapshot.shares:
            return
        margin = max(.01, snapshot.net_margin or snapshot.net_profit / snapshot.revenue)
        revenue = snapshot.revenue
        volume = 1.0
        price = revenue
        unit_cost = revenue * (1 - margin - .05)
        fixed_cost = revenue * .05
        multiples = {"bear": .88, "base": 1.0, "bull": 1.15}
        growth = snapshot.revenue_growth or 0
        for scenario, factor in multiples.items():
            growth_adjust = {"bear": max(-.15, growth - .10), "base": growth, "bull": growth + .10}[scenario]
            values = {
                "volume": volume * (1 + growth_adjust),
                "price": price,
                "unit_cost": unit_cost * ({"bear": 1.04, "base": 1.0, "bull": .97}[scenario]),
                "fixed_cost": fixed_cost,
                "tax_rate": .25,
                "shares": snapshot.shares,
                "valuation_multiple": (snapshot.pe or 20) * factor,
            }
            for variable, value in values.items():
                self.add_assumption(
                    company_id, variable, scenario, period, float(value),
                    rationale="Generated from latest company snapshot; replace with evidence-backed operating assumptions.",
                )

    def run_company(self, company_id: int, period: str = "next_year") -> dict:
        self.ensure_from_snapshot(company_id, period)
        assumptions = self.latest_assumptions(company_id, period)
        results = {}
        missing = {}
        for scenario in ("bear", "base", "bull"):
            variables = assumptions.get(scenario, {})
            absent = [x for x in self.REQUIRED if x not in variables]
            if absent:
                missing[scenario] = absent
                continue
            payload = {key: variables[key].value for key in self.REQUIRED}
            results[scenario] = run_financial_scenario(FinancialScenarioInput(**payload))
            results[scenario]["assumption_revisions"] = {key: variables[key].revision for key in self.REQUIRED}
        return {"company_id": company_id, "period": period, "scenarios": results, "missing": missing}
