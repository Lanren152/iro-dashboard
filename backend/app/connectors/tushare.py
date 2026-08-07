"""Tushare Pro HTTP connector.

This adapter intentionally uses Tushare's official HTTP API instead of the
`tushare` Python package, so the project keeps one HTTP dependency (`httpx`)
and can run in containers without an extra SDK.

Supported real-data domains:
- A-share security master (including listed, delisted and pending listings)
- Shenwan L1 industry membership
- Daily market/valuation snapshot
- Financial statement/indicator revisions published on a given announcement date
- Earnings forecast/express records as traceable source documents

The connector preserves announcement-date revisions with `version_key` and
separates market snapshots from financial snapshots with `data_kind`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

from .base import (
    CompanyInput,
    CompanySectorMembershipInput,
    CompanySnapshotInput,
    MetricObservationInput,
    SourceDocumentInput,
)


API_SOURCE_URL = "https://tushare.pro"


def _dt_yyyymmdd(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ratio_percent(value: Any) -> float | None:
    number = _num(value)
    return number / 100.0 if number is not None else None


class TushareConnector:
    name = "tushare_pro"

    def __init__(
        self,
        token: str,
        api_url: str = "http://api.tushare.pro",
        trade_date: str | None = None,
        announcement_date: str | None = None,
        data_dir: str | None = None,
        timeout_seconds: int = 90,
    ):
        if not token:
            raise ValueError("Tushare token is required")
        self.token = token
        self.api_url = api_url
        self.trade_date = trade_date
        self.announcement_date = announcement_date
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
        self._membership_rows: list[dict] | None = None

    def _call(self, api_name: str, params: dict | None = None, fields: str = "") -> list[dict]:
        payload = {
            "api_name": api_name,
            "token": self.token,
            "params": params or {},
            "fields": fields,
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.api_url, json=payload)
            response.raise_for_status()
            body = response.json()
        if body.get("code") != 0:
            raise RuntimeError(f"Tushare {api_name} failed: code={body.get('code')} msg={body.get('msg')}")
        data = body.get("data") or {}
        columns = data.get("fields") or []
        return [dict(zip(columns, row)) for row in data.get("items") or []]

    def _call_paged(
        self,
        api_name: str,
        params: dict | None = None,
        fields: str = "",
        page_size: int = 2000,
        max_pages: int = 100,
    ) -> list[dict]:
        rows: list[dict] = []
        seen_pages: set[str] = set()
        base = dict(params or {})
        for page in range(max_pages):
            page_params = dict(base)
            page_params.update({"limit": page_size, "offset": page * page_size})
            batch = self._call(api_name, page_params, fields)
            if not batch:
                break
            digest = hashlib.sha256(json.dumps(batch[:3], sort_keys=True, default=str).encode()).hexdigest()
            if digest in seen_pages:
                # Defensive stop for endpoints that ignore offset.
                break
            seen_pages.add(digest)
            rows.extend(batch)
            if len(batch) < page_size:
                break
        return rows

    def latest_open_trade_date(self, as_of: date | None = None) -> str:
        as_of = as_of or datetime.now(timezone.utc).date()
        start = as_of.replace(day=1).strftime("%Y%m%d")
        end = as_of.strftime("%Y%m%d")
        rows = self._call(
            "trade_cal",
            {"exchange": "SSE", "start_date": start, "end_date": end, "is_open": "1"},
            "cal_date,is_open",
        )
        dates = sorted(row["cal_date"] for row in rows if str(row.get("is_open")) == "1")
        if not dates:
            raise RuntimeError(f"No open trade date found between {start} and {end}")
        return dates[-1]

    def _industry_memberships(self) -> list[dict]:
        if self._membership_rows is None:
            self._membership_rows = self._call_paged(
                "index_member_all",
                {"is_new": "Y"},
                "l1_code,l1_name,l2_code,l2_name,l3_code,l3_name,ts_code,is_new",
                page_size=2000,
            )
        return self._membership_rows

    def _ticker_sector_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for row in self._industry_memberships():
            sector = self.sector_name_to_code.get(str(row.get("l1_name") or "").strip())
            if sector:
                out[str(row["ts_code"])] = sector
        return out

    def fetch_companies(self) -> list[CompanyInput]:
        sector_map = self._ticker_sector_map()
        combined: dict[str, dict] = {}
        fields = "ts_code,symbol,name,area,industry,market,exchange,list_status,list_date,delist_date,is_hs"
        for status in ("L", "D", "P"):
            for row in self._call_paged("stock_basic", {"exchange": "", "list_status": status}, fields, 5000):
                combined[str(row["ts_code"])] = row
        out: list[CompanyInput] = []
        for ticker, row in combined.items():
            sector_code = sector_map.get(ticker, self.fallback_sector)
            description = json.dumps(
                {
                    "area": row.get("area"),
                    "tushare_industry": row.get("industry"),
                    "market": row.get("market"),
                    "list_status": row.get("list_status"),
                    "list_date": row.get("list_date"),
                    "delist_date": row.get("delist_date"),
                },
                ensure_ascii=False,
            )
            out.append(
                CompanyInput(
                    ticker=ticker,
                    name=str(row.get("name") or ticker),
                    exchange=str(row.get("exchange") or ticker.split(".")[-1]),
                    sector_code=sector_code,
                    description=description,
                    is_demo=False,
                )
            )
        return out

    def fetch_company_memberships(self) -> list[CompanySectorMembershipInput]:
        out: list[CompanySectorMembershipInput] = []
        seen: set[tuple[str, str]] = set()
        for row in self._industry_memberships():
            ticker = str(row["ts_code"])
            l1_name = str(row.get("l1_name") or "").strip()
            sector_code = self.sector_name_to_code.get(l1_name)
            if not sector_code or (ticker, sector_code) in seen:
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
                    source_name="Tushare index_member_all",
                    is_demo=False,
                )
            )
        return out

    def _daily_market_snapshots(self) -> list[CompanySnapshotInput]:
        if not self.trade_date:
            return []
        rows = self._call_paged(
            "daily_basic",
            {"trade_date": self.trade_date},
            "ts_code,trade_date,close,pe,pb,total_share,total_mv",
            page_size=6000,
        )
        period = _dt_yyyymmdd(self.trade_date)
        return [
            CompanySnapshotInput(
                ticker=str(row["ts_code"]),
                period=period,
                data_kind="market",
                version_key=self.trade_date,
                shares=(_num(row.get("total_share")) or 0) * 10000 or None,
                price=_num(row.get("close")),
                market_cap=(_num(row.get("total_mv")) or 0) * 10000 or None,
                pe=_num(row.get("pe")),
                pb=_num(row.get("pb")),
                source_name="Tushare daily_basic",
                source_url=API_SOURCE_URL,
                is_demo=False,
            )
            for row in rows
        ]

    def _financial_snapshots(self) -> list[CompanySnapshotInput]:
        if not self.announcement_date:
            return []
        params = {"ann_date": self.announcement_date}
        income = self._call_paged(
            "income_vip", params,
            "ts_code,ann_date,f_ann_date,end_date,revenue,n_income_attr_p",
            page_size=5000,
        )
        balance = self._call_paged(
            "balancesheet_vip", params,
            "ts_code,ann_date,f_ann_date,end_date,total_liab,total_hldr_eqy_exc_min_int,total_share",
            page_size=5000,
        )
        cashflow = self._call_paged(
            "cashflow_vip", params,
            "ts_code,ann_date,f_ann_date,end_date,n_cashflow_act",
            page_size=5000,
        )
        indicator = self._call_paged(
            "fina_indicator_vip", params,
            "ts_code,ann_date,end_date,revenue_yoy,netprofit_yoy,grossprofit_margin,netprofit_margin,roe,debt_to_assets",
            page_size=5000,
        )
        merged: dict[tuple[str, str], dict] = {}
        for dataset in (income, balance, cashflow, indicator):
            for row in dataset:
                key = (str(row["ts_code"]), str(row["end_date"]))
                merged.setdefault(key, {}).update(row)
        out: list[CompanySnapshotInput] = []
        for (ticker, end_date), row in merged.items():
            version = str(row.get("f_ann_date") or row.get("ann_date") or self.announcement_date)
            out.append(
                CompanySnapshotInput(
                    ticker=ticker,
                    period=_dt_yyyymmdd(end_date),
                    data_kind="financial",
                    version_key=version,
                    revenue=_num(row.get("revenue")),
                    net_profit=_num(row.get("n_income_attr_p")),
                    operating_cash_flow=_num(row.get("n_cashflow_act")),
                    total_debt=_num(row.get("total_liab")),
                    net_assets=_num(row.get("total_hldr_eqy_exc_min_int")),
                    shares=_num(row.get("total_share")),
                    revenue_growth=_ratio_percent(row.get("revenue_yoy")),
                    profit_growth=_ratio_percent(row.get("netprofit_yoy")),
                    gross_margin=_ratio_percent(row.get("grossprofit_margin")),
                    net_margin=_ratio_percent(row.get("netprofit_margin")),
                    roe=_ratio_percent(row.get("roe")),
                    debt_ratio=_ratio_percent(row.get("debt_to_assets")),
                    source_name="Tushare financial_vip",
                    source_url=API_SOURCE_URL,
                    is_demo=False,
                )
            )
        return out

    def fetch_company_snapshots(self, since: datetime | None = None) -> list[CompanySnapshotInput]:
        rows = self._daily_market_snapshots() + self._financial_snapshots()
        return [row for row in rows if since is None or row.period >= since]

    def fetch_metrics(self, since: datetime | None = None) -> list[MetricObservationInput]:
        # Company fundamentals enter through CompanySnapshot. Industry-specific
        # metrics are intentionally provided by official/industrial adapters.
        return []

    def _announcement_documents(self, api_name: str, title_prefix: str) -> list[SourceDocumentInput]:
        if not self.announcement_date:
            return []
        rows = self._call_paged(api_name, {"ann_date": self.announcement_date}, "", 5000)
        out: list[SourceDocumentInput] = []
        for row in rows:
            ticker = str(row.get("ts_code") or "") or None
            text = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
            digest = hashlib.sha256(f"{api_name}:{text}".encode()).hexdigest()
            period = str(row.get("end_date") or row.get("period") or "") or None
            out.append(
                SourceDocumentInput(
                    source_type="licensed_financial_data",
                    source_name=f"Tushare {api_name}",
                    title=f"{title_prefix} {ticker or ''} {period or self.announcement_date}".strip(),
                    source_url=API_SOURCE_URL,
                    published_at=_dt_yyyymmdd(str(row.get("ann_date") or self.announcement_date)),
                    data_period=period,
                    company_ticker=ticker,
                    content_hash=digest,
                    parsed_text=text,
                    credibility=0.8,
                    is_demo=False,
                )
            )
        return out

    def fetch_documents(self, since: datetime | None = None) -> list[SourceDocumentInput]:
        documents = self._announcement_documents("forecast_vip", "业绩预告")
        documents += self._announcement_documents("express_vip", "业绩快报")
        return [row for row in documents if since is None or row.published_at >= since]
