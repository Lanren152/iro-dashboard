from datetime import datetime
from typing import Protocol

from pydantic import BaseModel


class CompanyInput(BaseModel):
    ticker: str
    name: str
    exchange: str
    sector_code: str
    description: str = ""
    market_cap: float | None = None
    pe: float | None = None
    is_demo: bool = False


class CompanySectorMembershipInput(BaseModel):
    ticker: str
    sector_code: str
    relationship_type: str = "primary"
    relevance: float = 1.0
    business_share: float = 1.0
    rationale: str = ""
    source_name: str = ""
    is_demo: bool = False


class CompanySnapshotInput(BaseModel):
    ticker: str
    period: datetime
    data_kind: str = "composite"
    version_key: str = ""
    revenue: float | None = None
    net_profit: float | None = None
    operating_cash_flow: float | None = None
    total_debt: float | None = None
    net_assets: float | None = None
    shares: float | None = None
    price: float | None = None
    market_cap: float | None = None
    pe: float | None = None
    pb: float | None = None
    revenue_growth: float | None = None
    profit_growth: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    roe: float | None = None
    debt_ratio: float | None = None
    order_growth: float | None = None
    contract_liability_growth: float | None = None
    capacity_utilization: float | None = None
    market_share: float | None = None
    business_purity: float | None = None
    source_name: str = ""
    source_url: str = ""
    is_demo: bool = False


class MetricObservationInput(BaseModel):
    metric_code: str
    period: datetime
    value: float
    source_name: str
    source_url: str = ""
    credibility: float = 0.5
    is_demo: bool = False


class SourceDocumentInput(BaseModel):
    source_type: str
    source_name: str
    title: str
    source_url: str = ""
    published_at: datetime
    data_period: str | None = None
    sector_code: str | None = None
    company_ticker: str | None = None
    content_hash: str
    raw_path: str = ""
    parsed_text: str
    credibility: float = 0.5
    is_demo: bool = False


class DataConnector(Protocol):
    name: str

    def fetch_companies(self) -> list[CompanyInput]: ...
    def fetch_company_memberships(self) -> list[CompanySectorMembershipInput]: ...
    def fetch_company_snapshots(self, since: datetime | None = None) -> list[CompanySnapshotInput]: ...
    def fetch_metrics(self, since: datetime | None = None) -> list[MetricObservationInput]: ...
    def fetch_documents(self, since: datetime | None = None) -> list[SourceDocumentInput]: ...
