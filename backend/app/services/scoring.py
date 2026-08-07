from dataclasses import dataclass

@dataclass
class OpportunitySignals:
    change_strength: float
    persistence: float
    profit_transmission: float
    evidence_quality: float
    underpricing: float
    business_purity: float
    competition_advantage: float
    falsifiability: float

WEIGHTS = {
    "change_strength": 0.15,
    "persistence": 0.15,
    "profit_transmission": 0.20,
    "evidence_quality": 0.10,
    "underpricing": 0.15,
    "business_purity": 0.10,
    "competition_advantage": 0.10,
    "falsifiability": 0.05,
}

def score_opportunity(s: OpportunitySignals) -> float:
    score = sum(getattr(s, key) * weight for key, weight in WEIGHTS.items())
    return round(max(0.0, min(100.0, score)), 2)
