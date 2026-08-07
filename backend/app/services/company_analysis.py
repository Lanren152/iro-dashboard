from datetime import datetime, timezone
from sqlalchemy import select

from ..db import AppSession as Session
from ..models import (
    Company,
    CompanySectorMembership,
    CompanySnapshot,
    Opportunity,
    OpportunityCompany,
)


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


class CompanyAnalysisService:
    def __init__(self, session: Session):
        self.session = session

    def latest_snapshot(self, company_id: int) -> CompanySnapshot | None:
        """Latest fundamentals snapshot; market-only rows must not shadow financials."""
        return self.session.exec(select(CompanySnapshot).where(
            CompanySnapshot.company_id == company_id,
            CompanySnapshot.data_kind.in_(["financial", "composite"]),
        ).order_by(CompanySnapshot.period.desc(), CompanySnapshot.version_key.desc())).first()

    def latest_market_snapshot(self, company_id: int) -> CompanySnapshot | None:
        return self.session.exec(select(CompanySnapshot).where(
            CompanySnapshot.company_id == company_id,
            CompanySnapshot.data_kind.in_(["market", "composite"]),
        ).order_by(CompanySnapshot.period.desc(), CompanySnapshot.version_key.desc())).first()

    def map_companies(self, opportunity: Opportunity, limit: int = 12) -> list[OpportunityCompany]:
        memberships = self.session.exec(select(CompanySectorMembership).where(
            CompanySectorMembership.sector_code == opportunity.sector_code
        )).all()
        if memberships:
            companies = [(self.session.get(Company, m.company_id), m) for m in memberships]
        else:
            raw = self.session.exec(select(Company).where(Company.sector_code == opportunity.sector_code)).all()
            companies = [(c, None) for c in raw]

        ranked: list[tuple[float, OpportunityCompany]] = []
        for company, membership in companies:
            if not company:
                continue
            snapshot = self.latest_snapshot(company.id)
            market_snapshot = self.latest_market_snapshot(company.id)
            purity = (snapshot.business_purity if snapshot and snapshot.business_purity is not None else (
                membership.business_share if membership else .5
            ))
            relevance = membership.relevance if membership else .7
            order = snapshot.order_growth if snapshot and snapshot.order_growth is not None else 0
            profit_growth = snapshot.profit_growth if snapshot and snapshot.profit_growth is not None else 0
            utilization = snapshot.capacity_utilization if snapshot and snapshot.capacity_utilization is not None else .5
            debt_ratio = snapshot.debt_ratio if snapshot and snapshot.debt_ratio is not None else .5
            ocf_quality = 0.5
            if snapshot and snapshot.net_profit not in (None, 0) and snapshot.operating_cash_flow is not None:
                ocf_quality = clamp(snapshot.operating_cash_flow / abs(snapshot.net_profit), 0, 1.5) / 1.5
            valuation = (
                market_snapshot.pe if market_snapshot and market_snapshot.pe and market_snapshot.pe > 0
                else (snapshot.pe if snapshot and snapshot.pe and snapshot.pe > 0 else company.pe)
            )
            valuation_score = 50 if not valuation else clamp(100 - max(0, valuation - 10) * 2.4)
            profit_elasticity = clamp((order * 110 + profit_growth * 90 + utilization * 35), 0, 100) / 100
            balance_score = clamp((1 - debt_ratio) * 100)
            cash_score = clamp(ocf_quality * 100)
            rank = (
                purity * 25 + relevance * 15 + profit_elasticity * 25 +
                balance_score * .15 + cash_score * .10 + valuation_score * .10
            )
            existing = self.session.exec(select(OpportunityCompany).where(
                OpportunityCompany.opportunity_id == opportunity.id,
                OpportunityCompany.company_id == company.id,
            )).first()
            payload = {
                "relevance": relevance,
                "business_purity": purity,
                "profit_elasticity": profit_elasticity,
                "balance_sheet_score": balance_score,
                "cash_quality_score": cash_score,
                "valuation_score": valuation_score,
                "ranking_score": rank,
                "rationale": (
                    f"业务纯度{purity:.0%}，利润弹性{profit_elasticity:.0%}，"
                    f"资产负债表{balance_score:.0f}，现金质量{cash_score:.0f}，估值{valuation_score:.0f}"
                ),
            }
            if existing:
                for key, value in payload.items():
                    setattr(existing, key, value)
                link = existing
            else:
                link = OpportunityCompany(opportunity_id=opportunity.id, company_id=company.id, **payload)
            ranked.append((rank, link))

        ranked.sort(key=lambda x: x[0], reverse=True)
        keep = ranked[:limit]
        for _, link in keep:
            self.session.add(link)
        self.session.commit()
        return [x[1] for x in keep]

    def company_driven_opportunities(self) -> list[Opportunity]:
        """Second discovery path: company anomalies can lead back to an industry direction."""
        results = []
        companies = self.session.exec(select(Company)).all()
        for company in companies:
            snapshots = self.session.exec(select(CompanySnapshot).where(
                CompanySnapshot.company_id == company.id,
                CompanySnapshot.data_kind.in_(["financial", "composite"]),
            ).order_by(CompanySnapshot.period, CompanySnapshot.version_key)).all()
            if len(snapshots) < 4:
                continue
            latest = snapshots[-1]
            previous = snapshots[-2]
            order_acceleration = (latest.order_growth or 0) - (previous.order_growth or 0)
            profit_acceleration = (latest.profit_growth or 0) - (previous.profit_growth or 0)
            cash_ok = bool(latest.net_profit and latest.operating_cash_flow is not None and latest.operating_cash_flow >= latest.net_profit * .65)
            if order_acceleration < .01 or profit_acceleration < .01 or not cash_ok:
                continue
            opportunity = self.session.exec(select(Opportunity).where(
                Opportunity.origin == "company",
                Opportunity.origin_company_id == company.id,
                Opportunity.stage != "archived",
            )).first()
            if not opportunity:
                opportunity = Opportunity(
                    title=f"{company.name}：订单与利润加速",
                    sector_code=company.sector_code,
                    origin="company",
                    origin_company_id=company.id,
                    stage="anomaly",
                    score=66,
                    confidence=.62,
                    thesis="公司订单、利润与现金流出现同步改善，需反向验证行业变化和竞争优势。",
                    profit_transmission="订单增长→收入增长；产能利用率与产品结构→利润率；现金流验证增长质量。",
                    missing_evidence="同行对比；客户与产能；市场隐含预期",
                    falsification_conditions="订单增速连续两个周期回落；经营现金流显著低于利润；市场份额下降",
                    is_demo=company.is_demo,
                    last_validated_at=datetime.now(timezone.utc),
                )
                self.session.add(opportunity)
                self.session.commit()
                self.session.refresh(opportunity)
            results.append(opportunity)
        return results
