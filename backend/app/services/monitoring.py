from datetime import datetime, timezone
from sqlalchemy import select

from ..db import AppSession as Session
from ..models import Evidence, Opportunity, StateTransition, SystemAlert
from .state_machine import validate_transition


class MonitoringService:
    def __init__(self, session: Session):
        self.session = session

    def review_all(self) -> dict:
        weakened = 0
        alerts = 0
        opportunities = self.session.exec(select(Opportunity).where(
            Opportunity.stage.in_(["deep_research", "candidate", "waiting_price", "weakened"])
        )).all()
        for opportunity in opportunities:
            evidence = self.session.exec(select(Evidence).where(
                Evidence.sector_code == opportunity.sector_code
            )).all()
            verified_negative = [x for x in evidence if x.verified and x.effect == "negative"]
            recent_positive = [x for x in evidence if x.effect == "positive"]
            if len(verified_negative) >= 2 and opportunity.stage != "weakened":
                self._move(opportunity, "weakened", "至少两条独立负面证据已通过验证")
                weakened += 1
                self.session.add(SystemAlert(
                    severity="high",
                    alert_type="logic_weakened",
                    subject_type="opportunity",
                    subject_id=str(opportunity.id),
                    title=f"投资逻辑削弱：{opportunity.title}",
                    details="；".join(x.claim for x in verified_negative[:3]),
                ))
                alerts += 1
            elif not recent_positive:
                exists = self.session.exec(select(SystemAlert).where(
                    SystemAlert.alert_type == "stale_evidence",
                    SystemAlert.subject_id == str(opportunity.id),
                    SystemAlert.status == "open",
                )).first()
                if not exists:
                    self.session.add(SystemAlert(
                        severity="medium",
                        alert_type="stale_evidence",
                        subject_type="opportunity",
                        subject_id=str(opportunity.id),
                        title=f"缺少新增验证：{opportunity.title}",
                        details="当前没有正面证据更新，继续观察而非自动维持原结论。",
                    ))
                    alerts += 1
        self.session.commit()
        return {"reviewed": len(opportunities), "weakened": weakened, "alerts_created": alerts}

    def _move(self, opportunity: Opportunity, target: str, reason: str) -> None:
        validate_transition(opportunity.stage, target)
        old = opportunity.stage
        opportunity.stage = target
        opportunity.updated_at = datetime.now(timezone.utc)
        self.session.add(StateTransition(
            opportunity_id=opportunity.id,
            from_stage=old,
            to_stage=target,
            reason=reason,
            actor="monitoring_agent",
        ))
        self.session.add(opportunity)
