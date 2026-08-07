from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .domain import AlertStatus, OpportunityOrigin, ResearchStage, TaskStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Sector(Base):
    __tablename__ = "sector"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    taxonomy_type: Mapped[str] = mapped_column(String(32), default="primary", index=True)
    parent_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")


class Company(Base):
    __tablename__ = "company"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    exchange: Mapped[str] = mapped_column(String(32), default="")
    sector_code: Mapped[str] = mapped_column(ForeignKey("sector.code"), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    market_cap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CompanySectorMembership(Base):
    __tablename__ = "company_sector_membership"
    __table_args__ = (UniqueConstraint("company_id", "sector_code", "relationship_type", name="uq_company_sector_relation"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    sector_code: Mapped[str] = mapped_column(ForeignKey("sector.code"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(32), default="primary", index=True)
    relevance: Mapped[float] = mapped_column(Float, default=1.0)
    business_share: Mapped[float] = mapped_column(Float, default=1.0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    source_name: Mapped[str] = mapped_column(String(200), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class CompanySnapshot(Base):
    __tablename__ = "company_snapshot"
    __table_args__ = (UniqueConstraint("company_id", "period", "source_name", "version_key", name="uq_company_snapshot_period_source_version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    period: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    data_kind: Mapped[str] = mapped_column(String(32), default="composite", index=True)
    version_key: Mapped[str] = mapped_column(String(64), default="")
    revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    operating_cash_flow: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_debt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    shares: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_cap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revenue_growth: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profit_growth: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gross_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    roe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    debt_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    order_growth: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    contract_liability_growth: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    capacity_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_share: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    business_purity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_name: Mapped[str] = mapped_column(String(200), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MetricDefinition(Base):
    __tablename__ = "metric_definition"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sector_code: Mapped[str] = mapped_column(ForeignKey("sector.code"), index=True)
    code: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(32), default="")
    frequency: Mapped[str] = mapped_column(String(32), default="monthly")
    positive_direction: Mapped[int] = mapped_column(Integer, default=1)
    signal_role: Mapped[str] = mapped_column(String(32), default="confirming", index=True)
    source_hint: Mapped[str] = mapped_column(Text, default="")


class MetricObservation(Base):
    __tablename__ = "metric_observation"
    __table_args__ = (UniqueConstraint("metric_code", "period", "source_name", name="uq_metric_period_source"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_code: Mapped[str] = mapped_column(ForeignKey("metric_definition.code"), index=True)
    period: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    value: Mapped[float] = mapped_column(Float)
    source_name: Mapped[str] = mapped_column(String(200), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    credibility: Mapped[float] = mapped_column(Float, default=0.5)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceDocument(Base):
    __tablename__ = "source_document"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    source_name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(500), index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    data_period: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sector_code: Mapped[Optional[str]] = mapped_column(ForeignKey("sector.code"), nullable=True, index=True)
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("company.id"), nullable=True, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    raw_path: Mapped[str] = mapped_column(Text, default="")
    parsed_text: Mapped[str] = mapped_column(Text, default="")
    credibility: Mapped[float] = mapped_column(Float, default=0.5)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sector_code: Mapped[str] = mapped_column(ForeignKey("sector.code"), index=True)
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("company.id"), nullable=True, index=True)
    source_document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("source_document.id"), nullable=True, index=True)
    metric_observation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("metric_observation.id"), nullable=True, index=True)
    claim: Mapped[str] = mapped_column(Text)
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    data_period: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    variable: Mapped[str] = mapped_column(String(120), index=True)
    effect: Mapped[str] = mapped_column(String(32), default="unknown")
    evidence_type: Mapped[str] = mapped_column(String(64), default="fact")
    source_rank: Mapped[int] = mapped_column(Integer, default=6)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    independent_path: Mapped[str] = mapped_column(String(160), default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Opportunity(Base):
    __tablename__ = "opportunity"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    sector_code: Mapped[str] = mapped_column(ForeignKey("sector.code"), index=True)
    origin: Mapped[str] = mapped_column(String(32), default=OpportunityOrigin.MARKET.value, index=True)
    origin_company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("company.id"), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(64), default=ResearchStage.WATCH.value, index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    thesis: Mapped[str] = mapped_column(Text, default="")
    profit_transmission: Mapped[str] = mapped_column(Text, default="")
    market_pricing: Mapped[str] = mapped_column(Text, default="")
    missing_evidence: Mapped[str] = mapped_column(Text, default="")
    falsification_conditions: Mapped[str] = mapped_column(Text, default="")
    last_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OpportunityCompany(Base):
    __tablename__ = "opportunity_company"
    __table_args__ = (UniqueConstraint("opportunity_id", "company_id", name="uq_opportunity_company"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunity.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    business_purity: Mapped[float] = mapped_column(Float, default=0.0)
    profit_elasticity: Mapped[float] = mapped_column(Float, default=0.0)
    balance_sheet_score: Mapped[float] = mapped_column(Float, default=0.0)
    cash_quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    valuation_score: Mapped[float] = mapped_column(Float, default=0.0)
    ranking_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    rationale: Mapped[str] = mapped_column(Text, default="")


class ProfitDriver(Base):
    __tablename__ = "profit_driver"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_company_profit_driver"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("profit_driver.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(200))
    driver_type: Mapped[str] = mapped_column(String(64), default="other")
    unit: Mapped[str] = mapped_column(String(32), default="")
    formula: Mapped[str] = mapped_column(Text, default="")
    sign: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(200), default="system")


class ProfitAssumption(Base):
    __tablename__ = "profit_assumption"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    opportunity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("opportunity.id"), nullable=True, index=True)
    variable: Mapped[str] = mapped_column(String(120), index=True)
    scenario: Mapped[str] = mapped_column(String(32), index=True)
    period: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32), default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_ids: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MarketExpectation(Base):
    __tablename__ = "market_expectation"
    __table_args__ = (UniqueConstraint("company_id", "as_of", "source_name", name="uq_market_expectation"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    price: Mapped[float] = mapped_column(Float)
    current_eps: Mapped[float] = mapped_column(Float)
    exit_pe: Mapped[float] = mapped_column(Float, default=20.0)
    horizon_years: Mapped[int] = mapped_column(Integer, default=3)
    required_return: Mapped[float] = mapped_column(Float, default=0.15)
    implied_eps_growth: Mapped[float] = mapped_column(Float)
    consensus_eps_growth: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    valuation_percentile: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_name: Mapped[str] = mapped_column(String(200), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResearchTask(Base):
    __tablename__ = "research_task"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(120), index=True)
    subject_type: Mapped[str] = mapped_column(String(64), index=True)
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.PENDING.value, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_run"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(120), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(120), default="")
    task_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    input_digest: Mapped[str] = mapped_column(String(64), default="")
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="completed")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StateTransition(Base):
    __tablename__ = "state_transition"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunity.id"), index=True)
    from_stage: Mapped[str] = mapped_column(String(64))
    to_stage: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SystemAlert(Base):
    __tablename__ = "system_alert"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    severity: Mapped[str] = mapped_column(String(16), default="info", index=True)
    alert_type: Mapped[str] = mapped_column(String(64), index=True)
    subject_type: Mapped[str] = mapped_column(String(64), index=True)
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(300))
    details: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default=AlertStatus.OPEN.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchReport(Base):
    __tablename__ = "research_report"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cadence: Mapped[str] = mapped_column(String(32), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    title: Mapped[str] = mapped_column(String(300))
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PredictionSnapshot(Base):
    __tablename__ = "prediction_snapshot"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunity.id"), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    horizon_days: Mapped[int] = mapped_column(Integer, default=90)
    predicted_score: Mapped[float] = mapped_column(Float)
    predicted_stage: Mapped[str] = mapped_column(String(64))
    predicted_metric: Mapped[str] = mapped_column(String(120), default="")
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
