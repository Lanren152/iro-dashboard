from enum import StrEnum


class ResearchStage(StrEnum):
    WATCH = "watch"
    ANOMALY = "anomaly"
    INDUSTRY_VALIDATION = "industry_validation"
    COMPANY_MAPPING = "company_mapping"
    DEEP_RESEARCH = "deep_research"
    CANDIDATE = "candidate"
    WAITING_PRICE = "waiting_price"
    WEAKENED = "weakened"
    FALSIFIED = "falsified"
    ARCHIVED = "archived"


class EvidenceEffect(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class EvidenceType(StrEnum):
    FACT = "fact"
    MANAGEMENT_GUIDANCE = "management_guidance"
    THIRD_PARTY = "third_party"
    MEDIA_LEAD = "media_lead"
    AI_INFERENCE = "ai_inference"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class OpportunityOrigin(StrEnum):
    MARKET = "market"
    COMPANY = "company"
    MANUAL = "manual"
