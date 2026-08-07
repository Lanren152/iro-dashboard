from collections import defaultdict
from datetime import datetime, timezone
from sqlalchemy import select

from ..db import AppSession as Session
from ..models import Evidence, MetricObservation, SourceDocument


SOURCE_RANKS = {
    "exchange_disclosure": 1,
    "official_statistics": 1,
    "licensed_industry": 2,
    "peer_disclosure": 3,
    "management_guidance": 4,
    "research_report": 5,
    "media": 5,
    "demo": 6,
    "ai_inference": 6,
}


def source_rank(source_type: str, credibility: float) -> int:
    base = SOURCE_RANKS.get(source_type, 5)
    if credibility >= .9:
        return min(base, 2)
    if credibility < .4:
        return max(base, 6)
    return base


class EvidenceService:
    def __init__(self, session: Session):
        self.session = session

    def from_metric_signal(self, sector_code: str, signal: dict) -> list[Evidence]:
        created: list[Evidence] = []
        observations = signal.get("latest_observations") or []
        if not observations and signal.get("observation_id"):
            obs = self.session.get(MetricObservation, signal["observation_id"])
            if obs:
                observations = [{
                    "id": obs.id, "source_name": obs.source_name, "credibility": obs.credibility,
                    "is_demo": obs.is_demo, "period": obs.period, "value": obs.value,
                }]
        for obs_data in observations:
            obs = self.session.get(MetricObservation, obs_data["id"])
            if not obs:
                continue
            claim = (
                f"{signal['metric_name']}出现异常，最新值{obs.value}{signal['unit']}，"
                f"方向{signal['direction']}，持续性{signal.get('persistence', 0):.2f}"
            )
            exists = self.session.exec(select(Evidence).where(
                Evidence.metric_observation_id == obs.id,
                Evidence.variable == signal["metric_code"],
            )).first()
            if exists:
                created.append(exists)
                continue
            item = Evidence(
                sector_code=sector_code,
                metric_observation_id=obs.id,
                claim=claim,
                source_excerpt=claim,
                data_period=obs.period.date().isoformat(),
                variable=signal["metric_code"],
                effect="positive",
                evidence_type="third_party",
                source_rank=source_rank("demo" if obs.is_demo else "licensed_industry", obs.credibility),
                confidence=min(.9, .45 + abs(signal["z_score"]) * .07 + signal.get("persistence", 0) * .15),
                independent_path=f"{obs.source_name}::{signal['metric_code']}",
                verified=False,
                observed_at=obs.period,
            )
            self.session.add(item)
            self.session.flush()
            created.append(item)
        return created

    def extract_documents(self) -> int:
        """Create traceable evidence records from source documents.

        This deterministic fallback keeps provenance intact. When an LLM extractor is configured,
        its structured claims can be inserted through the same table and verification logic.
        """
        created = 0
        documents = self.session.exec(select(SourceDocument)).all()
        for doc in documents:
            if not doc.sector_code:
                continue
            sentence = doc.parsed_text.strip().replace("\n", " ")[:500]
            if not sentence:
                continue
            variable = self._classify_variable(sentence)
            effect = "negative" if any(k in sentence for k in ("下降", "恶化", "亏损", "压力", "风险")) else "mixed"
            exists = self.session.exec(select(Evidence).where(
                Evidence.source_document_id == doc.id,
                Evidence.variable == variable,
            )).first()
            if exists:
                continue
            self.session.add(Evidence(
                sector_code=doc.sector_code,
                company_id=doc.company_id,
                source_document_id=doc.id,
                claim=sentence,
                source_excerpt=sentence,
                data_period=doc.data_period,
                variable=variable,
                effect=effect,
                evidence_type="fact" if doc.source_type in {"exchange_disclosure", "official_statistics"} else "third_party",
                source_rank=source_rank(doc.source_type, doc.credibility),
                confidence=doc.credibility,
                independent_path=f"{doc.source_name}::{doc.source_type}",
                verified=False,
                observed_at=doc.published_at,
            ))
            created += 1
        self.session.commit()
        self.refresh_verification()
        return created

    def refresh_verification(self) -> int:
        evidence = self.session.exec(select(Evidence)).all()
        groups: dict[tuple[str, int | None, str, str], list[Evidence]] = defaultdict(list)
        for item in evidence:
            groups[(item.sector_code, item.company_id, item.variable, item.effect)].append(item)
        changed = 0
        for items in groups.values():
            paths = {x.independent_path for x in items if x.independent_path}
            high_quality = [x for x in items if x.source_rank <= 3]
            verified = len(paths) >= 2 and bool(high_quality or len(paths) >= 3)
            for item in items:
                if item.verified != verified:
                    item.verified = verified
                    self.session.add(item)
                    changed += 1
        self.session.commit()
        return changed

    def summary(self, sector_code: str, company_id: int | None = None) -> dict:
        stmt = select(Evidence).where(Evidence.sector_code == sector_code)
        if company_id is not None:
            stmt = stmt.where(Evidence.company_id == company_id)
        items = self.session.exec(stmt).all()
        return {
            "total": len(items),
            "verified": sum(1 for x in items if x.verified),
            "independent_paths": len({x.independent_path for x in items if x.independent_path}),
            "high_quality": sum(1 for x in items if x.source_rank <= 3),
            "positive": sum(1 for x in items if x.effect == "positive"),
            "negative": sum(1 for x in items if x.effect == "negative"),
            "items": items,
        }

    @staticmethod
    def _classify_variable(text: str) -> str:
        rules = [
            ("订单", "order_growth"), ("合同负债", "contract_liability"), ("产能", "capacity"),
            ("库存", "inventory"), ("价格", "price"), ("成本", "cost"), ("毛利", "margin"),
            ("现金流", "cash_flow"), ("份额", "market_share"), ("需求", "demand"),
        ]
        for token, variable in rules:
            if token in text:
                return variable
        return "general"
