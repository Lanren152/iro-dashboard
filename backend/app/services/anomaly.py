from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass
class AnomalyResult:
    metric_code: str
    latest: float
    z_score: float
    trend: float
    persistence: float
    triggered: bool
    direction: str


def detect_anomaly(metric_code: str, values: list[float], positive_direction: int = 1) -> AnomalyResult:
    if len(values) < 6:
        return AnomalyResult(metric_code, values[-1] if values else 0, 0, 0, 0, False, "insufficient")
    baseline = values[:-1]
    latest = values[-1]
    sigma = pstdev(baseline) or 1.0
    z = (latest - mean(baseline)) / sigma
    recent = values[-4:]
    changes = [(recent[i] - recent[i - 1]) * positive_direction for i in range(1, len(recent))]
    positive_steps = sum(1 for x in changes if x > 0)
    persistence = positive_steps / max(1, len(changes))
    trend = (recent[-1] - recent[0]) * positive_direction
    adjusted_z = z * positive_direction
    triggered = adjusted_z >= 1.15 and trend > 0 and persistence >= 2 / 3
    direction = "improving" if trend > 0 else "deteriorating"
    return AnomalyResult(metric_code, latest, round(z, 3), round(trend, 3), round(persistence, 3), triggered, direction)
