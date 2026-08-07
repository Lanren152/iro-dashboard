from datetime import datetime, timezone
from sqlalchemy import select

from ..db import AppSession as Session
from ..models import Opportunity, PredictionSnapshot


class EvaluationService:
    def __init__(self, session: Session):
        self.session = session

    def snapshot_opportunities(self) -> int:
        opportunities = self.session.exec(select(Opportunity)).all()
        count = 0
        for opportunity in opportunities:
            exists = self.session.exec(select(PredictionSnapshot).where(
                PredictionSnapshot.opportunity_id == opportunity.id,
                PredictionSnapshot.predicted_stage == opportunity.stage,
                PredictionSnapshot.predicted_score == opportunity.score,
                PredictionSnapshot.evaluated_at.is_(None),
            )).first()
            if exists:
                continue
            self.session.add(PredictionSnapshot(
                opportunity_id=opportunity.id,
                predicted_score=opportunity.score,
                predicted_stage=opportunity.stage,
                predicted_metric="opportunity_score",
                target_value=opportunity.score,
            ))
            count += 1
        self.session.commit()
        return count

    def evaluate_score(self, snapshot_id: int, actual_value: float) -> PredictionSnapshot:
        item = self.session.get(PredictionSnapshot, snapshot_id)
        if not item:
            raise ValueError("Prediction snapshot not found")
        item.actual_value = actual_value
        item.error = actual_value - (item.target_value or 0)
        item.evaluated_at = datetime.now(timezone.utc)
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item
