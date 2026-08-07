from __future__ import annotations

from datetime import datetime, timezone

from ..config import get_settings
from ..connectors.akshare import AkshareConnector
from ..connectors.baostock import BaostockConnector
from ..connectors.tushare import TushareConnector
from ..db import AppSession as Session
from .ingestion import IngestionService


def sync_tushare(
    session: Session,
    trade_date: str | None = None,
    announcement_date: str | None = None,
    include_master: bool = True,
) -> dict:
    settings = get_settings()
    if not settings.tushare_token:
        raise RuntimeError("TUSHARE_TOKEN is not configured")
    connector = TushareConnector(
        token=settings.tushare_token,
        api_url=settings.tushare_api_url,
        trade_date=trade_date,
        announcement_date=announcement_date,
    )
    if trade_date is None:
        trade_date = connector.latest_open_trade_date()
        connector.trade_date = trade_date
    if announcement_date is None:
        announcement_date = datetime.now(timezone.utc).strftime("%Y%m%d")
        connector.announcement_date = announcement_date

    if not include_master:
        connector.fetch_companies = lambda: []  # type: ignore[method-assign]
        connector.fetch_company_memberships = lambda: []  # type: ignore[method-assign]

    result = IngestionService(session).ingest(connector)
    return {
        "provider": "tushare",
        "trade_date": trade_date,
        "announcement_date": announcement_date,
        "include_master": include_master,
        **result,
    }


def sync_akshare(
    session: Session,
    report_date: str | None = None,
    include_master: bool = True,
    include_deep_dive: bool = False,
    max_deep_dive: int | None = None,
) -> dict:
    """Sync free akshare data: full-market forecast signals + security master.

    First pass pulls the full-market earnings forecast batch (fast) plus the
    security master and Shenwan membership from akshare/EM endpoints.
    ``include_deep_dive`` is OFF by default because the akshare/Sina financial
    endpoints rate-limit after ~100 companies; financial deep-dive now runs
    through ``sync_valuation`` (baostock), which is not rate-limited.
    """
    settings = get_settings()
    if report_date is None:
        report_date = settings.akshare_report_date or None
    connector = AkshareConnector(
        report_date=report_date,
        forecast_filter=(
            settings.akshare_forecast_min_pre,
            settings.akshare_forecast_max_pre,
        ),
        max_deep_dive=(
            max_deep_dive if max_deep_dive is not None else settings.akshare_max_deep_dive
        ),
    )
    if not include_master:
        connector.fetch_companies = lambda: []  # type: ignore[method-assign]
        connector.fetch_company_memberships = lambda: []  # type: ignore[method-assign]
    if not include_deep_dive:
        connector.fetch_company_snapshots = lambda since=None: []  # type: ignore[method-assign]

    result = IngestionService(session).ingest(connector)
    triggered = len(connector._triggered_ticker_set())
    return {
        "provider": "akshare",
        "report_date": connector.report_date,
        "include_master": include_master,
        "include_deep_dive": include_deep_dive,
        "forecast_triggered": triggered,
        **result,
    }


def sync_valuation(
    session: Session,
    report_date: str | None = None,
    trade_date: str | None = None,
    tickers: list[str] | None = None,
    max_tickers: int | None = None,
) -> dict:
    """Sync baostock financial + market snapshots for triggered companies.

    Pulls quarterly financials (revenue/profit/growth/margins/ROE/debt) and
    market data (price / PE / PB / shares / market cap) from baostock for the
    companies triggered by an earnings-forecast signal (or an explicit
    ``tickers`` list). Baostock is the primary financial source because the
    akshare/Sina financial endpoints rate-limit after a ~100-company batch.
    """
    settings = get_settings()
    ak = None
    if tickers is None:
        # Reuse akshare's forecast trigger set to know which companies to price.
        if report_date is None:
            report_date = settings.akshare_report_date or None
        ak = AkshareConnector(
            report_date=report_date,
            forecast_filter=(
                settings.akshare_forecast_min_pre,
                settings.akshare_forecast_max_pre,
            ),
            max_deep_dive=settings.akshare_max_deep_dive,
        )
        tickers = list(ak._triggered_ticker_set())
    if max_tickers and ak is not None:
        # Keep the same prioritisation akshare uses: biggest forecast change first.
        ordered = ak._deep_dive_order()
        tickers = ordered[:max_tickers]

    connector = BaostockConnector(
        tickers=tickers,
        trade_date=trade_date or settings.baostock_trade_date or None,
    )
    result = IngestionService(session).ingest(connector)
    return {
        "provider": "baostock",
        "trade_date": connector.trade_date,
        "tickers_requested": len(tickers),
        **result,
    }
