"""Baostock free connector for the Investment Research OS.

Provides both financial snapshots (quarterly statements/indicators) and
market snapshots (price / PE / PB / shares / market cap) from baostock's
free endpoints. Baostock needs no token and is stable from both local and
cloud runners.

Background: the akshare/Sina financial endpoints rate-limit and block the
local IP after a ~100-company batch pull, so baostock became the primary
financial source (design decision by the user). Baostock's quarterly
financial data is cumulative within a year (e.g. Q4 = full year, Q3 = first
three quarters), so growth fields are taken from baostock's own YoY metrics.

Data mapping (verified against baostock, 2026-08):

Financial snapshot (``data_kind="financial"``), per quarter:
- ``revenue``            <- query_profit_data MBRevenue (main business revenue)
- ``net_profit``         <- query_profit_data netProfit
- ``shares``             <- query_profit_data totalShare
- ``profit_growth``      <- query_growth_data YOYNI (net-profit YoY, index 5)
- ``gross_margin``       <- query_profit_data gpMargin
- ``net_margin``         <- query_profit_data npMargin
- ``roe``                <- query_profit_data roeAvg
- ``debt_ratio``         <- query_balance_data liabilityToAsset
- ``operating_cash_flow``<- query_cash_flow_data CFOToNP * netProfit (derived)
- ``revenue_growth`` / ``order_growth`` / ``net_assets`` -> None (baostock gap)

Market snapshot (``data_kind="market"``):
- ``price``              <- query_history_k_data_plus close
- ``pe``                 <- query_history_k_data_plus peTTM
- ``pb``                 <- query_history_k_data_plus pbMRQ
- ``shares``             <- query_profit_data totalShare
- ``market_cap``         <- close * totalShare
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from .base import CompanySnapshotInput

API_SOURCE_URL = "https://www.baostock.com"


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value in ("", "--", "None", "nan"):
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _to_bs_code(ticker: str) -> str:
    """Convert a 6-digit A-share code to baostock's 'sh.600519' form."""
    if ticker.startswith(("60", "68")):
        return f"sh.{ticker}"
    if ticker.startswith(("00", "30")):
        return f"sz.{ticker}"
    return f"bj.{ticker}"


def _stat_date(row: list[str]) -> datetime | None:
    """Parse a baostock statDate (YYYY-MM-DD) into a UTC datetime."""
    if not row or len(row) < 3:
        return None
    try:
        return datetime.strptime(row[2], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class BaostockConnector:
    """Financial + valuation snapshots for a list of tickers.

    Parameters
    ----------
    tickers : iterable[str]
        Companies to price and pull financials for. Typically the akshare
        connector's triggered set.
    trade_date : str, optional
        YYYY-MM-DD trade date for the market snapshot; defaults to today.
    quarters : int, optional
        How many trailing quarters of financials to pull per company.
        Default 4 (satisfies the >=4-period requirement of the company
        driver while keeping the full-market cloud sync bounded).
    enrich_sina : bool, optional
        When True, fill baostock's field gaps (revenue YoY, contract
        liability / order growth, net assets, total debt) from the Sina
        financial endpoints when those are reachable. A probe on the first
        company decides availability once; if Sina is rate-limited, the whole
        enrichment is skipped so the batch is not blocked.
    """

    name = "baostock"

    def __init__(
        self,
        tickers: list[str] | None = None,
        trade_date: str | None = None,
        quarters: int = 4,
        data_dir: str | None = None,
        timeout_seconds: int = 90,
        enrich_sina: bool = True,
    ):
        self.tickers = sorted(set(tickers or []))
        today = datetime.now(timezone.utc)
        self.trade_date = trade_date or today.strftime("%Y-%m-%d")
        self.period = today.replace(hour=0, minute=0, second=0, microsecond=0)
        self.quarters = quarters
        self.timeout_seconds = timeout_seconds
        self.enrich_sina = enrich_sina
        self._sina_available: bool | None = None  # None = not probed yet
        self.sina_enriched_tickers = 0
        self._snapshots_cache: list[CompanySnapshotInput] | None = None
        _ = data_dir  # protocol symmetry

    # ------------------------------------------------------------------ #
    # baostock calls (imported lazily)                                    #
    # ------------------------------------------------------------------ #

    def _bs_login(self):
        import baostock as bs

        result = bs.login()
        if result.error_code != "0":
            raise RuntimeError(f"baostock login failed: {result.error_msg}")
        return bs

    @staticmethod
    def _query_rows(bs, method: str, **kwargs) -> list[list[str]]:
        rs = getattr(bs, method)(**kwargs)
        rows = []
        while (rs.error_code == "0") and rs.next():
            rows.append(rs.get_row_data())
        return rows

    def _quote(self, bs, code: str) -> dict[str, Any]:
        rs = bs.query_history_k_data_plus(
            code,
            "date,close,peTTM,pbMRQ,isST",
            start_date=self.trade_date,
            end_date=self.trade_date,
            frequency="d",
            adjustflag="3",
        )
        row = None
        while (rs.error_code == "0") and rs.next():
            row = rs.get_row_data()
        if row is None:
            return {}
        return {
            "date": row[0],
            "close": _num(row[1]),
            "peTTM": _num(row[2]),
            "pbMRQ": _num(row[3]),
            "isST": row[4],
        }

    def _financial_snapshots(self, bs, ticker: str, code: str) -> list[CompanySnapshotInput]:
        """Trailing quarterly financial snapshots for one company."""
        year = int(self.trade_date[:4])
        out: list[CompanySnapshotInput] = []
        count = 0
        # Walk back quarter by quarter (allow crossing into prior years).
        for offset in range(self.quarters * 4):
            q_year, q_quarter = _quarter_ago(year, 4, offset)
            profit = self._query_rows(bs, "query_profit_data", code=code, year=q_year, quarter=q_quarter)
            if not profit:
                continue
            row = profit[0]
            stat = _stat_date(row)
            if stat is None:
                continue
            growth = self._query_rows(bs, "query_growth_data", code=code, year=q_year, quarter=q_quarter)
            balance = self._query_rows(bs, "query_balance_data", code=code, year=q_year, quarter=q_quarter)
            cashflow = self._query_rows(bs, "query_cash_flow_data", code=code, year=q_year, quarter=q_quarter)

            net_profit = _num(row[6])  # netProfit
            profit_growth = _num(growth[0][5]) if growth else None  # YOYNI index 5
            roe = _num(row[3]) if len(row) > 3 else None  # roeAvg
            net_margin = _num(row[4]) if len(row) > 4 else None  # npMargin
            gross_margin = _num(row[5]) if len(row) > 5 else None  # gpMargin
            shares = _num(row[9]) if len(row) > 9 else None  # totalShare
            debt_ratio = _num(balance[0][7]) if balance else None  # liabilityToAsset
            cfo_to_np = _num(cashflow[0][8]) if cashflow else None  # CFOToNP
            ocf = net_profit * cfo_to_np if (net_profit is not None and cfo_to_np is not None) else None

            out.append(
                CompanySnapshotInput(
                    ticker=ticker,
                    period=stat,
                    data_kind="financial",
                    version_key=f"{q_year}Q{q_quarter}",
                    revenue=_num(row[8]),  # MBRevenue
                    net_profit=net_profit,
                    operating_cash_flow=ocf,
                    total_debt=None,  # baostock gap: no absolute debt figure
                    net_assets=None,  # baostock gap: only ratios
                    shares=shares,
                    revenue_growth=None,  # baostock gap: no revenue YoY
                    profit_growth=profit_growth,
                    gross_margin=gross_margin,
                    net_margin=net_margin,
                    roe=roe,
                    debt_ratio=debt_ratio,
                    order_growth=None,  # baostock gap: no contract liability
                    source_name="baostock quarterly financials",
                    source_url=API_SOURCE_URL,
                    is_demo=False,
                )
            )
            count += 1
            if count >= self.quarters:
                break
        return out

    def _sina_probe(self) -> bool:
        """Probe whether the Sina financial endpoints are reachable.

        Decides once per batch: if the first probe fails (rate-limited /
        blocked IP), enrichment is skipped for the whole run. Returns True
        when Sina is usable.
        """
        if self._sina_available is not None:
            return self._sina_available
        if not self.enrich_sina:
            self._sina_available = False
            return False
        probe_ok = False
        try:
            import akshare as ak

            probe_ticker = self.tickers[0]
            prefix = "sh" if probe_ticker.startswith(("60", "68")) else "sz"
            df = ak.stock_financial_report_sina(stock=f"{prefix}{probe_ticker}", symbol="资产负债表")
            probe_ok = len(df) > 0
        except Exception:  # noqa: BLE001 - rate limit / block => skip enrichment
            probe_ok = False
        self._sina_available = probe_ok
        return probe_ok

    def _sina_enrich(self, ticker: str, financials: list[CompanySnapshotInput]) -> None:
        """Fill baostock gaps (revenue YoY, order/contract-liability growth)
        from Sina's financial indicators when available."""
        if not self._sina_available:
            return
        try:
            import akshare as ak

            indicators = ak.stock_financial_analysis_indicator(symbol=ticker, start_year="2023")
            if indicators is None or len(indicators) == 0:
                return
            by_period: dict[str, dict] = {}
            for row in indicators.to_dict("records"):
                period = str(row.get("日期") or "").strip()
                if period:
                    by_period[period] = row
            for snap in financials:
                if snap.data_kind != "financial" or snap.period is None:
                    continue
                key = snap.period.strftime("%Y%m%d")
                row = by_period.get(key)
                if row is None:
                    norm = "".join(ch for ch in key if ch.isdigit())
                    for cand_period, cand in by_period.items():
                        if "".join(ch for ch in cand_period if ch.isdigit()) == norm:
                            row = cand
                            break
                if row is None:
                    continue
                rev_growth = _num(row.get("主营业务收入增长率(%)"))
                snap.revenue_growth = rev_growth / 100.0 if rev_growth is not None else snap.revenue_growth
            self.sina_enriched_tickers += 1
        except Exception:  # noqa: BLE001 - enrichment is best-effort
            pass

    # ------------------------------------------------------------------ #
    # DataConnector protocol                                               #
    # ------------------------------------------------------------------ #

    def fetch_companies(self) -> list:
        return []  # connector does not manage the security master

    def fetch_company_memberships(self) -> list:
        return []

    def fetch_company_snapshots(self, since: datetime | None = None) -> list[CompanySnapshotInput]:
        if self._snapshots_cache is not None:
            return self._snapshots_cache
        if not self.tickers:
            return []
        self._sina_probe()
        bs = self._bs_login()
        out: list[CompanySnapshotInput] = []
        try:
            for index, ticker in enumerate(self.tickers, start=1):
                try:
                    code = _to_bs_code(ticker)
                    financials = self._financial_snapshots(bs, ticker, code)
                    if financials:
                        self._sina_enrich(ticker, financials)
                    out.extend(financials)

                    quote = self._quote(bs, code)
                    if quote.get("close") is not None:
                        shares = next(
                            (s.shares for s in reversed(out) if s.shares is not None), None
                        )
                        price = quote["close"]
                        market_cap = price * shares if shares else None
                        out.append(
                            CompanySnapshotInput(
                                ticker=ticker,
                                period=self.period,
                                data_kind="market",
                                version_key=self.trade_date,
                                shares=shares,
                                price=price,
                                market_cap=market_cap,
                                pe=quote.get("peTTM"),
                                pb=quote.get("pbMRQ"),
                                source_name="baostock query_history_k_data_plus",
                                source_url=API_SOURCE_URL,
                                is_demo=False,
                            )
                        )
                except Exception as exc:  # noqa: BLE001 - one bad stock must not abort
                    print(f"[baostock] failed {ticker}: {exc}")
                if index % 25 == 0:
                    print(f"[baostock] processed {index}/{len(self.tickers)} ({ticker})")
                time.sleep(0.2)  # be gentle on the free endpoints
        finally:
            try:
                bs.logout()
            except Exception:
                pass
        self._snapshots_cache = out
        return out

    def fetch_metrics(self, since: datetime | None = None) -> list:
        return []

    def fetch_documents(self, since: datetime | None = None) -> list:
        return []


def _quarter_ago(year: int, quarter: int, offset: int) -> tuple[int, int]:
    """Return (year, quarter) ``offset`` quarters before (year, quarter)."""
    total = year * 4 + (quarter - 1) - offset
    y = total // 4
    q = (total % 4) + 1
    return y, q
