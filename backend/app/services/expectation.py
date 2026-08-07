from math import pow
from datetime import datetime, timezone
from sqlalchemy import select

from ..db import AppSession as Session
from ..models import CompanySnapshot, MarketExpectation


def reverse_implied_growth(price: float, current_eps: float, exit_pe: float = 20, years: int = 3, required_return: float = .15) -> float:
    if price <= 0 or current_eps <= 0 or exit_pe <= 0 or years <= 0:
        raise ValueError("price, current_eps, exit_pe and years must be positive")
    future_price_required = price * pow(1 + required_return, years)
    future_eps_required = future_price_required / exit_pe
    return pow(future_eps_required / current_eps, 1 / years) - 1


class ExpectationService:
    def __init__(self, session: Session):
        self.session = session

    def refresh_company(self, company_id: int, exit_pe: float = 20, years: int = 3, required_return: float = .15) -> MarketExpectation | None:
        market = self.session.exec(select(CompanySnapshot).where(
            CompanySnapshot.company_id == company_id,
            CompanySnapshot.data_kind.in_(["market", "composite"]),
        ).order_by(CompanySnapshot.period.desc(), CompanySnapshot.version_key.desc())).first()
        financial = self.session.exec(select(CompanySnapshot).where(
            CompanySnapshot.company_id == company_id,
            CompanySnapshot.data_kind.in_(["financial", "composite"]),
        ).order_by(CompanySnapshot.period.desc(), CompanySnapshot.version_key.desc())).first()
        if not market or not financial or not market.price or not financial.net_profit or not financial.shares:
            return None
        eps = financial.net_profit / financial.shares
        if eps <= 0:
            return None
        growth = reverse_implied_growth(market.price, eps, exit_pe, years, required_return)
        existing = self.session.exec(select(MarketExpectation).where(
            MarketExpectation.company_id == company_id,
            MarketExpectation.as_of == market.period,
            MarketExpectation.source_name == market.source_name,
        )).first()
        if existing:
            return existing
        item = MarketExpectation(
            company_id=company_id,
            as_of=market.period,
            price=market.price,
            current_eps=eps,
            exit_pe=exit_pe,
            horizon_years=years,
            required_return=required_return,
            implied_eps_growth=growth,
            consensus_eps_growth=None,
            valuation_percentile=None,
            source_name=market.source_name,
            source_url=market.source_url,
            is_demo=market.is_demo or financial.is_demo,
        )
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item
