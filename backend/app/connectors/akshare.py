"""Akshare free-data connector for the Investment Research OS.

Replaces the paid Tushare connector with free akshare endpoints so the
research pipeline can run without a Tushare token. Implements the same
``DataConnector`` protocol as ``tushare.py``.

Data mapping (all verified against akshare 1.18.54):

- ``fetch_companies``          -> stock_info_a_code_name()  (full A-share list)
- ``fetch_company_memberships``-> sw_index_first_info() + sw_index_third_cons()
                                 (Shenwan L1 industry membership)
- ``fetch_company_snapshots``  -> layered: only companies that triggered a
                                 forecast anomaly get financial deep-dive
- ``fetch_metrics``            -> stock_yjyg_em()  (earnings forecast signals)
- ``fetch_documents``          -> forecast records as source documents

Layering strategy (the core design decision): the first pass pulls the
full-market earnings forecast batch (fast). The second pass deep-dives into
financial statements only for companies whose forecast shows a big profit
change (pre-increase >50% or pre-decrease/widening loss). This avoids pulling
financials for all ~5500 A-shares every run.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .base import (
    CompanyInput,
    CompanySectorMembershipInput,
    CompanySnapshotInput,
    MetricObservationInput,
    SourceDocumentInput,
)

API_SOURCE_URL = "https://akshare.akfamily.xyz"


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


def _ratio_percent(value: Any) -> float | None:
    number = _num(value)
    return number / 100.0 if number is not None else None


def _period_key(value: Any) -> str:
    """Normalise a report-period value to YYYYMMDD (first 8 digits).

    Handles '20251231', '2025-12-31', datetime.date and Timestamp forms.
    """
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[:8]


def _dt(value: Any) -> datetime | None:
    """Parse a 'YYYY-MM-DD' or 'YYYYMMDD' or 'YYYY/MM/DD' string to UTC datetime."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class AkshareConnector:
    """Feed the IRO pipeline from free akshare endpoints.

    Parameters
    ----------
    report_date : str, optional
        The report period to pull earnings forecasts for, in YYYYMMDD form
        (e.g. ``20260630`` for the 2026 half-year). Defaults to the latest
        period akshare returns for ``stock_yjyg_em``.
    forecast_filter : tuple, optional
        (min_pre_increase_pct, max_pre_decrease_pct) used to decide which
        companies get a financial deep-dive. Default (50.0, -10.0).
    max_deep_dive : int, optional
        Cap on how many companies get the financial deep-dive per run.
        Default 300.
    data_dir : str, optional
        Directory holding sectors.json. Defaults to the repo data/ dir.
    """

    name = "akshare_free"

    def __init__(
        self,
        report_date: str | None = None,
        forecast_filter: tuple[float, float] = (50.0, -10.0),
        max_deep_dive: int = 300,
        data_dir: str | None = None,
        timeout_seconds: int = 90,
    ):
        self.report_date = report_date
        self.forecast_filter = forecast_filter
        self.max_deep_dive = max_deep_dive
        self.timeout_seconds = timeout_seconds

        root = Path(data_dir) if data_dir else Path(__file__).resolve().parents[3] / "data"
        sectors_path = root / "sectors.json"
        sectors = json.loads(sectors_path.read_text(encoding="utf-8"))
        self.sector_name_to_code = {
            str(row["name"]).strip(): str(row["code"])
            for row in sectors
            if row.get("taxonomy_type") == "primary"
        }
        self.fallback_sector = self.sector_name_to_code.get("综合", "40")

        self._companies_cache: list[CompanyInput] | None = None
        self._membership_cache: list[CompanySectorMembershipInput] | None = None
        self._forecast_cache: list[dict] | None = None
        self._triggered_tickers: set[str] | None = None
        self._ticker_forecast_change: dict[str, float] = {}

    # ------------------------------------------------------------------ #
    # akshare calls (imported lazily so the module loads without akshare) #
    # ------------------------------------------------------------------ #

    def _ak(self):
        import akshare as ak

        return ak

    def _fetch_forecast_rows(self) -> list[dict]:
        """Full-market earnings forecast batch. Returns raw dict rows."""
        if self._forecast_cache is not None:
            return self._forecast_cache
        ak = self._ak()
        report_date = self.report_date
        # akshare's stock_yjyg_em expects the report period, e.g. 20260630.
        # If none given, fall back to today's year+0630/1231 heuristic.
        if not report_date:
            today = datetime.now(timezone.utc)
            report_date = f"{today.year}0630" if today.month >= 7 else f"{today.year - 1}1231"
        # The EM endpoint is intermittently blocked from cloud runners, so
        # retry before falling back to the prior period.
        df = None
        for attempt in range(3):
            try:
                df = ak.stock_yjyg_em(date=report_date)
                break
            except Exception as exc:  # noqa: BLE001 - retry then try prior period
                print(f"[akshare] stock_yjyg_em({report_date}) attempt {attempt + 1} failed: {exc}")
                if attempt < 2:
                    time.sleep(2)
        if df is None or len(df) == 0:
            # The requested period may have no forecasts yet; try the prior one.
            alt = f"{int(report_date[:4]) - 1}1231"
            df = ak.stock_yjyg_em(date=alt)
        rows = df.to_dict("records")
        self._forecast_cache = rows
        self.report_date = report_date
        return rows

    def _triggered_ticker_set(self) -> set[str]:
        """Companies whose forecast implies a material profit change.

        Also records the per-ticker forecast change magnitude so the deep-dive
        prioritises the biggest profit movers (not code order).
        """
        if self._triggered_tickers is not None:
            return self._triggered_tickers
        min_pre, max_pre = self.forecast_filter
        triggered: set[str] = set()
        self._ticker_forecast_change: dict[str, float] = {}
        for row in self._fetch_forecast_rows():
            code = str(row.get("股票代码") or "").strip()
            if not code:
                continue
            indicator = str(row.get("预测指标") or "")
            if "净利润" not in indicator and "归母" not in indicator:
                # Only profit-line forecasts drive the signal.
                continue
            pct = _num(row.get("业绩变动幅度"))
            ftype = str(row.get("预告类型") or "")
            if pct is None:
                continue
            if pct >= min_pre or pct <= max_pre or ftype in ("预减", "增亏", "首亏"):
                triggered.add(code)
                # Keep the largest-magnitude change for prioritisation.
                prev = abs(self._ticker_forecast_change.get(code, 0.0))
                if abs(pct) > prev:
                    self._ticker_forecast_change[code] = pct
        self._triggered_tickers = triggered
        return triggered

    def _deep_dive_order(self) -> list[str]:
        """Triggered tickers sorted by |forecast change| descending."""
        self._triggered_ticker_set()
        ordered = sorted(
            self._triggered_tickers,
            key=lambda t: abs(self._ticker_forecast_change.get(t, 0.0)),
            reverse=True,
        )
        if self.max_deep_dive and len(ordered) > self.max_deep_dive:
            ordered = ordered[: self.max_deep_dive]
        return ordered

    # ------------------------------------------------------------------ #
    # DataConnector protocol                                               #
    # ------------------------------------------------------------------ #

    def fetch_companies(self) -> list[CompanyInput]:
        if self._companies_cache is not None:
            return self._companies_cache
        # Primary: akshare/EM full A-share list. EM is intermittently blocked
        # from cloud runners (ConnectionReset), so retry then fall back to
        # baostock's query_all_stock (verified reachable from GitHub Actions).
        df = None
        ak = self._ak()
        for attempt in range(3):
            try:
                df = ak.stock_info_a_code_name()
                break
            except Exception as exc:  # noqa: BLE001 - retry then fall back
                print(f"[akshare] stock_info_a_code_name attempt {attempt + 1} failed: {exc}")
                if attempt < 2:
                    time.sleep(2)
        source = "akshare stock_info_a_code_name"
        if df is None or len(df) == 0:
            df = self._baostock_all_stocks()
            source = "baostock query_all_stock"
        out: list[CompanyInput] = []
        for row in df.to_dict("records"):
            ticker = str(row.get("code") or "").strip()
            name = str(row.get("name") or "").strip()
            if not ticker or not name:
                continue
            exchange = "sh" if ticker.startswith(("60", "68")) else (
                "sz" if ticker.startswith(("00", "30")) else "bj"
            )
            out.append(
                CompanyInput(
                    ticker=ticker,
                    name=name,
                    exchange=exchange,
                    sector_code=self.fallback_sector,
                    description=f"来源：{source}",
                    is_demo=False,
                )
            )
        self._companies_cache = out
        return out

    def _baostock_all_stocks(self) -> Any:
        """Fallback full A-share list via baostock (cloud-reachable).

        Returns a pandas DataFrame with columns code/name, mirroring the
        akshare list shape (code without exchange prefix, plain name).
        """
        import baostock as bs

        lg = bs.login()
        if lg.error_code != "0":
            raise RuntimeError(f"baostock login failed: {lg.error_msg}")
        try:
            import pandas as pd

            # baostock requires an explicit trading day; walk back to the most
            # recent weekday (skips weekends; A-share holidays are rare enough
            # that the weekday fallback is acceptable for the security master).
            day = datetime.now()
            for _ in range(10):
                if day.weekday() < 5:  # Mon-Fri
                    break
                day = day - timedelta(days=1)
            rs = bs.query_all_stock(day=day.strftime("%Y-%m-%d"))
            rows = []
            while (rs.error_code == "0") and rs.next():
                row = rs.get_row_data()
                # row: [code('sh.600519'), tradeStatus, name]
                code = row[0]
                name = row[2]
                # Keep A-share stocks (drop indices like sh.000001 which are
                # index codes too; baostock marks tradeStatus='1' for all).
                if code.startswith(("sh.6", "sh.68", "sz.0", "sz.3", "bj.")):
                    # Strip the exchange prefix: sh.600519 -> 600519
                    rows.append({"code": code.split(".")[-1], "name": name})
            return pd.DataFrame(rows)
        finally:
            try:
                bs.logout()
            except Exception:
                pass

    def fetch_company_memberships(self) -> list[CompanySectorMembershipInput]:
        if self._membership_cache is not None:
            return self._membership_cache
        import re

        ak = self._ak()
        out: list[CompanySectorMembershipInput] = []
        seen: set[tuple[str, str]] = set()
        try:
            industries = ak.sw_index_first_info()
            for _, ind in industries.iterrows():
                l1_name = str(ind.get("行业名称") or "").strip()
                sector_code = self.sector_name_to_code.get(l1_name)
                if not sector_code:
                    continue
                # sw_index_first_info returns e.g. '801010.SI'; index_component_sw
                # wants the bare '801010' index code.
                index_code = re.sub(r"\..*$", "", str(ind.get("行业代码") or ""))
                if not index_code:
                    continue
                try:
                    members = ak.index_component_sw(symbol=index_code)
                except Exception:
                    continue
                for _, m in members.iterrows():
                    ticker = str(m.get("证券代码") or "").strip()
                    if not ticker or (ticker, sector_code) in seen:
                        continue
                    seen.add((ticker, sector_code))
                    out.append(
                        CompanySectorMembershipInput(
                            ticker=ticker,
                            sector_code=sector_code,
                            relationship_type="primary",
                            relevance=1.0,
                            business_share=1.0,
                            rationale=f"申万一级行业：{l1_name}",
                            source_name="akshare index_component_sw",
                            is_demo=False,
                        )
                    )
        except Exception:
            # Industry membership is a nice-to-have; failures must not kill sync.
            pass
        self._membership_cache = out
        return out

    def fetch_company_snapshots(self, since: datetime | None = None) -> list[CompanySnapshotInput]:
        """Layered financial deep-dive for triggered companies only."""
        if not self._triggered_ticker_set():
            return []
        ordered = self._deep_dive_order()
        out: list[CompanySnapshotInput] = []
        for index, ticker in enumerate(ordered, start=1):
            try:
                out.extend(self._company_snapshots(ticker))
            except Exception as exc:  # noqa: BLE001 - one bad company must not abort the batch
                print(f"[akshare] deep-dive failed {ticker}: {exc}")
            if index % 20 == 0:
                print(f"[akshare] deep-dive {index}/{len(ordered)} ({ticker})")
            time.sleep(0.2)  # be gentle on the free endpoints
        return out

    def _company_snapshots(self, ticker: str) -> list[CompanySnapshotInput]:
        """Financial statements + indicators for one company, as snapshots."""
        ak = self._ak()
        prefix = "sh" if ticker.startswith(("60", "68")) else "sz"
        stock_key = f"{prefix}{ticker}"

        income = ak.stock_financial_report_sina(stock=stock_key, symbol="利润表")
        balance = ak.stock_financial_report_sina(stock=stock_key, symbol="资产负债表")
        cashflow = ak.stock_financial_report_sina(stock=stock_key, symbol="现金流量表")
        indicators = ak.stock_financial_analysis_indicator(symbol=ticker, start_year="2023")

        # Index income/balance/cashflow by report date for merging.
        income_by_period: dict[str, dict[str, Any]] = {}
        for row in income.to_dict("records"):
            period = str(row.get("报告日") or "").strip()
            if period:
                income_by_period[period] = row
        balance_by_period: dict[str, dict[str, Any]] = {}
        for row in balance.to_dict("records"):
            period = str(row.get("报告日") or "").strip()
            if period:
                balance_by_period[period] = row
        cashflow_by_period: dict[str, dict[str, Any]] = {}
        for row in cashflow.to_dict("records"):
            period = str(row.get("报告日") or "").strip()
            if period:
                cashflow_by_period[period] = row

        indicator_by_period: dict[str, dict[str, Any]] = {}
        for row in indicators.to_dict("records"):
            period = str(row.get("日期") or "").strip()
            if period:
                indicator_by_period[period] = row

        # Merge every period that appears in the income statement.
        # Pre-compute year-over-year growth from the income statement itself so
        # the latest period (e.g. 2026-06-30 interim report) still has growth
        # figures even when the indicator feed lags a period behind.
        period_revenue: dict[str, float | None] = {}
        period_profit: dict[str, float | None] = {}
        period_contract_liability: dict[str, float | None] = {}
        for period, income_row in income_by_period.items():
            period_revenue[period] = _num(income_row.get("营业收入"))
            period_profit[period] = _num(income_row.get("归属于母公司的净利润"))
            if period_profit[period] is None:
                period_profit[period] = _num(income_row.get("净利润"))
            period_contract_liability[period] = _num(balance_by_period.get(period, {}).get("合同负债"))

        def _self_growth(values: dict[str, float | None], period: str) -> float | None:
            """(this period / same period last year) - 1, or None."""
            current = values.get(period)
            if current is None or current == 0:
                return None
            if len(period) != 8:
                return None
            last_year = f"{int(period[:4]) - 1}{period[4:]}"
            base = values.get(last_year)
            if base is None or base == 0:
                return None
            return current / base - 1.0

        out: list[CompanySnapshotInput] = []
        for period, income_row in income_by_period.items():
            dtime = _dt(period)
            if dtime is None:
                continue
            bal = balance_by_period.get(period, {})
            cf = cashflow_by_period.get(period, {})
            # Indicator periods may be formatted differently (e.g. 20250630 vs
            # 2025-06-30 vs Timestamp); match by normalised YYYYMMDD key.
            ind = indicator_by_period.get(period)
            if ind is None:
                key = _period_key(period)
                for cand_period, cand in indicator_by_period.items():
                    if _period_key(cand_period) == key:
                        ind = cand
                        break

            revenue = period_revenue.get(period)
            net_profit = period_profit.get(period)

            ocf = _num(cf.get("经营活动产生的现金流量净额"))
            total_debt = _num(bal.get("负债合计"))
            net_assets = _num(bal.get("股东权益"))
            shares = _num(bal.get("股本"))

            revenue_growth = _ratio_percent(ind.get("主营业务收入增长率(%)") if ind else None)
            profit_growth = _ratio_percent(ind.get("净利润增长率(%)") if ind else None)
            if revenue_growth is None:
                revenue_growth = _self_growth(period_revenue, period)
            if profit_growth is None:
                profit_growth = _self_growth(period_profit, period)
            # Contract liabilities are booked (prepaid) orders: their growth is
            # a leading proxy for forward demand, standing in for IRO's
            # order_growth input (akshare exposes no direct order series).
            order_growth = _self_growth(period_contract_liability, period)

            out.append(
                CompanySnapshotInput(
                    ticker=ticker,
                    period=dtime,
                    data_kind="financial",
                    version_key=period,
                    revenue=revenue,
                    net_profit=net_profit,
                    operating_cash_flow=ocf,
                    total_debt=total_debt,
                    net_assets=net_assets,
                    shares=shares,
                    revenue_growth=revenue_growth,
                    profit_growth=profit_growth,
                    order_growth=order_growth,
                    gross_margin=_ratio_percent(ind.get("销售毛利率(%)") if ind else None),
                    net_margin=_ratio_percent(ind.get("销售净利率(%)") if ind else None),
                    roe=_ratio_percent(ind.get("净资产收益率(%)") if ind else None),
                    debt_ratio=_ratio_percent(ind.get("资产负债率(%)") if ind else None),
                    source_name="akshare stock_financial_report_sina",
                    source_url=API_SOURCE_URL,
                    is_demo=False,
                )
            )
        return out

    def fetch_metrics(self, since: datetime | None = None) -> list[MetricObservationInput]:
        """Earnings-forecast signals as metric observations.

        Each forecast row (company x profit-line indicator) becomes a metric
        observation with code ``forecast_earnings_growth`` so the radar can
        aggregate and detect anomalies. The value is the forecast change %.
        """
        out: list[MetricObservationInput] = []
        for row in self._fetch_forecast_rows():
            ticker = str(row.get("股票代码") or "").strip()
            pct = _num(row.get("业绩变动幅度"))
            ann_date = _dt(row.get("公告日期"))
            if not ticker or pct is None or ann_date is None:
                continue
            indicator = str(row.get("预测指标") or "")
            if "净利润" not in indicator and "归母" not in indicator:
                continue
            out.append(
                MetricObservationInput(
                    metric_code="forecast_earnings_growth",
                    period=ann_date.replace(hour=0, minute=0, second=0, microsecond=0),
                    value=pct,
                    source_name="akshare stock_yjyg_em",
                    source_url=API_SOURCE_URL,
                    credibility=0.6,
                    is_demo=False,
                )
            )
        return out

    def fetch_documents(self, since: datetime | None = None) -> list[SourceDocumentInput]:
        """Forecast records as source documents for the evidence system."""
        out: list[SourceDocumentInput] = []
        for row in self._fetch_forecast_rows():
            ticker = str(row.get("股票代码") or "").strip()
            if not ticker:
                continue
            indicator = str(row.get("预测指标") or "")
            if "净利润" not in indicator and "归母" not in indicator:
                continue
            ann_date = _dt(row.get("公告日期"))
            if ann_date is None:
                continue
            period = str(row.get("公告日期") or "")
            text = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
            digest = hashlib.sha256(f"forecast:{ticker}:{indicator}:{period}".encode()).hexdigest()
            out.append(
                SourceDocumentInput(
                    source_type="licensed_financial_data",
                    source_name="akshare stock_yjyg_em",
                    title=f"业绩预告 {ticker} {indicator} {period}",
                    source_url=API_SOURCE_URL,
                    published_at=ann_date,
                    data_period=period,
                    company_ticker=ticker,
                    content_hash=digest,
                    parsed_text=text,
                    credibility=0.7,
                    is_demo=False,
                )
            )
        return out
