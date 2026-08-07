from ..domain import ResearchStage


ALLOWED = {
    ResearchStage.WATCH.value: {ResearchStage.ANOMALY.value, ResearchStage.ARCHIVED.value},
    ResearchStage.ANOMALY.value: {ResearchStage.INDUSTRY_VALIDATION.value, ResearchStage.WATCH.value, ResearchStage.FALSIFIED.value},
    ResearchStage.INDUSTRY_VALIDATION.value: {ResearchStage.COMPANY_MAPPING.value, ResearchStage.WATCH.value, ResearchStage.FALSIFIED.value},
    ResearchStage.COMPANY_MAPPING.value: {ResearchStage.DEEP_RESEARCH.value, ResearchStage.WATCH.value, ResearchStage.FALSIFIED.value},
    ResearchStage.DEEP_RESEARCH.value: {ResearchStage.CANDIDATE.value, ResearchStage.WAITING_PRICE.value, ResearchStage.WEAKENED.value, ResearchStage.FALSIFIED.value},
    ResearchStage.CANDIDATE.value: {ResearchStage.WAITING_PRICE.value, ResearchStage.WEAKENED.value, ResearchStage.FALSIFIED.value},
    ResearchStage.WAITING_PRICE.value: {ResearchStage.CANDIDATE.value, ResearchStage.WEAKENED.value, ResearchStage.FALSIFIED.value},
    ResearchStage.WEAKENED.value: {ResearchStage.DEEP_RESEARCH.value, ResearchStage.FALSIFIED.value, ResearchStage.ARCHIVED.value},
    ResearchStage.FALSIFIED.value: {ResearchStage.ARCHIVED.value, ResearchStage.WATCH.value},
    ResearchStage.ARCHIVED.value: {ResearchStage.WATCH.value},
}

PROGRESSION = [
    ResearchStage.WATCH.value,
    ResearchStage.ANOMALY.value,
    ResearchStage.INDUSTRY_VALIDATION.value,
    ResearchStage.COMPANY_MAPPING.value,
    ResearchStage.DEEP_RESEARCH.value,
]


def validate_transition(current: str, target: str) -> None:
    if target == current:
        return
    if target not in ALLOWED.get(current, set()):
        raise ValueError(f"Invalid state transition: {current} -> {target}")


def next_progression_steps(current: str, target: str) -> list[str]:
    """Return only forward sequential states, making repeated research cycles idempotent."""
    if current == target:
        return []
    if current not in PROGRESSION or target not in PROGRESSION:
        return [target]
    current_index = PROGRESSION.index(current)
    target_index = PROGRESSION.index(target)
    if current_index >= target_index:
        return []
    return PROGRESSION[current_index + 1: target_index + 1]
