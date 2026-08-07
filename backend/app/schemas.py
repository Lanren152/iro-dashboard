from datetime import datetime
from pydantic import BaseModel, Field


class FinancialScenarioInput(BaseModel):
    volume: float = Field(gt=0)
    price: float
    unit_cost: float
    fixed_cost: float = 0
    tax_rate: float = Field(default=0.25, ge=0, le=1)
    shares: float = Field(gt=0)
    valuation_multiple: float = Field(gt=0)


class ProfitAssumptionInput(BaseModel):
    variable: str
    scenario: str
    period: str = "next_year"
    value: float
    unit: str = ""
    rationale: str = ""
    evidence_ids: list[int] = Field(default_factory=list)
    opportunity_id: int | None = None


class ReverseExpectationInput(BaseModel):
    price: float = Field(gt=0)
    current_eps: float = Field(gt=0)
    exit_pe: float = Field(default=20, gt=0)
    years: int = Field(default=3, gt=0, le=20)
    required_return: float = Field(default=.15, ge=0, le=1)


class HypothesisInput(BaseModel):
    title: str
    sector_code: str
    thesis: str
    origin_company_id: int | None = None
    evidence_ids: list[int] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    falsification_conditions: list[str] = Field(default_factory=list)


class StateChangeInput(BaseModel):
    stage: str
    reason: str
    actor: str = "agent"


class DocumentInput(BaseModel):
    source_type: str
    source_name: str
    title: str
    source_url: str = ""
    published_at: datetime
    data_period: str | None = None
    sector_code: str | None = None
    company_ticker: str | None = None
    raw_path: str = ""
    parsed_text: str
    credibility: float = Field(default=0.5, ge=0, le=1)
    is_demo: bool = False


class MetricInput(BaseModel):
    metric_code: str
    period: datetime
    value: float
    source_name: str
    source_url: str = ""
    credibility: float = Field(default=.5, ge=0, le=1)
    is_demo: bool = False


class CompanyMembershipInput(BaseModel):
    ticker: str
    sector_code: str
    relationship_type: str = "primary"
    relevance: float = Field(default=1, ge=0, le=1)
    business_share: float = Field(default=1, ge=0, le=1)
    rationale: str = ""
    source_name: str = ""
    is_demo: bool = False


class CompanySnapshotInput(BaseModel):
    ticker: str
    period: datetime
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


class PredictionEvaluationInput(BaseModel):
    actual_value: float
