import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from ..db import AppSession as Session
from ..models import Opportunity, ResearchReport, StateTransition, SystemAlert


class ReportingService:
    def __init__(self, session: Session):
        self.session = session

    def generate(self, cadence: str = "daily") -> ResearchReport:
        now = datetime.now(timezone.utc)
        start = now - (timedelta(days=1) if cadence == "daily" else timedelta(days=7))
        opportunities = self.session.exec(select(Opportunity).order_by(Opportunity.score.desc())).all()
        transitions = self.session.exec(select(StateTransition).where(
            StateTransition.created_at >= start
        ).order_by(StateTransition.created_at.desc())).all()
        alerts = self.session.exec(select(SystemAlert).where(
            SystemAlert.status == "open"
        ).order_by(SystemAlert.created_at.desc())).all()
        summary = {
            "top_opportunities": [{
                "id": x.id, "title": x.title, "stage": x.stage, "score": x.score,
                "confidence": x.confidence, "is_demo": x.is_demo,
            } for x in opportunities[:10]],
            "state_changes": [{
                "opportunity_id": x.opportunity_id, "from": x.from_stage, "to": x.to_stage, "reason": x.reason,
            } for x in transitions[:20]],
            "open_alerts": [{
                "id": x.id, "severity": x.severity, "title": x.title, "details": x.details,
            } for x in alerts[:20]],
            "no_qualified_new_opportunity": not any(x.stage == "candidate" and not x.is_demo for x in opportunities),
        }
        report = ResearchReport(
            cadence=cadence,
            period_start=start,
            period_end=now,
            title=f"{cadence.capitalize()} Investment Research Brief",
            summary_json=json.dumps(summary, ensure_ascii=False),
        )
        self.session.add(report)
        self.session.commit()
        self.session.refresh(report)
        return report
