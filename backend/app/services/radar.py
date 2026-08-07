from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean
from sqlalchemy import select

from ..db import AppSession as Session
from ..models import MetricDefinition, MetricObservation, Opportunity, Sector
from ..domain import OpportunityOrigin, ResearchStage
from .anomaly import detect_anomaly
from .evidence import EvidenceService
from .scoring import OpportunitySignals, score_opportunity


class MarketRadar:
    def __init__(self, session: Session):
        self.session = session
        self.evidence = EvidenceService(session)

    def scan(self) -> list[dict]:
        definitions = self.session.exec(select(MetricDefinition)).all()
        by_sector: dict[str, list[dict]] = defaultdict(list)
        for definition in definitions:
            obs = self.session.exec(select(MetricObservation).where(
                MetricObservation.metric_code == definition.code
            ).order_by(MetricObservation.period)).all()
            if not obs:
                continue
            by_period: dict[datetime, list[MetricObservation]] = defaultdict(list)
            for item in obs:
                by_period[item.period].append(item)
            periods = sorted(by_period)
            values = [mean(x.value for x in by_period[period]) for period in periods]
            result = detect_anomaly(definition.code, values, definition.positive_direction)
            if result.triggered:
                latest_items = by_period[periods[-1]]
                signal = result.__dict__ | {
                    "metric_name": definition.name,
                    "unit": definition.unit,
                    "signal_role": definition.signal_role,
                    "latest_observations": [{
                        "id": x.id, "source_name": x.source_name, "credibility": x.credibility,
                        "is_demo": x.is_demo, "period": x.period, "value": x.value,
                    } for x in latest_items],
                    "source_name": "; ".join(sorted({x.source_name for x in latest_items})),
                    "credibility": mean(x.credibility for x in latest_items),
                    "is_demo": all(x.is_demo for x in latest_items),
                }
                by_sector[definition.sector_code].append(signal)

        results = []
        for sector_code, signals in by_sector.items():
            if len(signals) < 2:
                continue
            sector = self.session.get(Sector, sector_code)
            opportunity = self.session.exec(select(Opportunity).where(
                Opportunity.sector_code == sector_code,
                Opportunity.origin == OpportunityOrigin.MARKET.value,
                Opportunity.stage != ResearchStage.ARCHIVED.value,
            )).first()
            avg_z = mean(abs(x["z_score"]) for x in signals)
            avg_persistence = mean(x["persistence"] for x in signals)
            avg_credibility = mean(x["credibility"] for x in signals)
            score = score_opportunity(OpportunitySignals(
                change_strength=min(100, 40 + avg_z * 18 + len(signals) * 4),
                persistence=avg_persistence * 100,
                profit_transmission=min(85, 50 + len({x["signal_role"] for x in signals}) * 8),
                evidence_quality=avg_credibility * 100,
                underpricing=50,
                business_purity=50,
                competition_advantage=50,
                falsifiability=75,
            ))
            is_demo = all(x["is_demo"] for x in signals)
            if not opportunity:
                opportunity = Opportunity(
                    title=f"{sector.name if sector else sector_code}：多指标同步异常",
                    sector_code=sector_code,
                    origin=OpportunityOrigin.MARKET.value,
                    stage=ResearchStage.ANOMALY.value,
                    score=score,
                    confidence=min(.88, .4 + avg_persistence * .2 + avg_credibility * .2 + len(signals) * .03),
                    thesis="至少两个行业指标出现持续同步改善，需要验证供需、利润传导和市场定价。",
                    profit_transmission="需求、价差、库存、订单与产能利用率通过销量和单位利润传导。",
                    market_pricing="尚未完成公司级市场隐含预期测算。",
                    missing_evidence="供给扩张；公司业务纯度；公司财务质量；市场隐含预期",
                    falsification_conditions="关键指标连续两个周期反向；供给增速明显超过需求；利润与现金流不匹配",
                    is_demo=is_demo,
                    last_validated_at=datetime.now(timezone.utc),
                    next_review_at=datetime.now(timezone.utc) + timedelta(days=30),
                )
                self.session.add(opportunity)
                self.session.commit()
                self.session.refresh(opportunity)
            else:
                opportunity.score = score
                opportunity.confidence = min(.9, .4 + avg_persistence * .2 + avg_credibility * .2 + len(signals) * .03)
                opportunity.is_demo = is_demo
                opportunity.last_validated_at = datetime.now(timezone.utc)
                opportunity.updated_at = datetime.now(timezone.utc)
                self.session.add(opportunity)
                self.session.commit()

            evidence_ids = []
            for signal in signals:
                evidence_ids.extend(x.id for x in self.evidence.from_metric_signal(sector_code, signal))
            self.session.commit()
            self.evidence.refresh_verification()
            results.append({
                "opportunity_id": opportunity.id,
                "sector_code": sector_code,
                "sector_name": sector.name if sector else sector_code,
                "signals": signals,
                "evidence_ids": evidence_ids,
                "score": score,
                "is_demo": opportunity.is_demo,
                "origin": opportunity.origin,
            })
        return results
