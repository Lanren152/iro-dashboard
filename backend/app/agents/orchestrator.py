import hashlib
import json
import time
from datetime import datetime, timezone
from sqlalchemy import select

from ..db import AppSession as Session
from ..models import (
    AgentRun,
    Company,
    Evidence,
    Opportunity,
    OpportunityCompany,
    PredictionSnapshot,
    ResearchTask,
    StateTransition,
    SystemAlert,
)
from ..domain import ResearchStage, TaskStatus
from ..services.company_analysis import CompanyAnalysisService
from ..services.evaluation import EvaluationService
from ..services.evidence import EvidenceService
from ..services.expectation import ExpectationService
from ..services.financial import FinancialModelService
from ..services.monitoring import MonitoringService
from ..services.profit_tree import ProfitTreeService
from ..services.radar import MarketRadar
from ..services.reporting import ReportingService
from ..services.state_machine import next_progression_steps, validate_transition
from .providers import ResearchProvider, analyze_with_retry, get_provider


class ResearchOrchestrator:
    def __init__(self, session: Session, provider: ResearchProvider | None = None):
        self.session = session
        self.provider = provider or get_provider()
        self.evidence = EvidenceService(session)
        self.company_analysis = CompanyAnalysisService(session)
        self.profit_tree = ProfitTreeService(session)
        self.financial = FinancialModelService(session)
        self.expectation = ExpectationService(session)

    def run_cycle(self) -> dict:
        started = time.perf_counter()
        extracted = self.evidence.extract_documents()
        radar_results = MarketRadar(self.session).scan()
        company_origin = self.company_analysis.company_driven_opportunities()
        # Company-driven opportunities enter the same pipeline even when no industry metric triggered today.
        known_ids = {x["opportunity_id"] for x in radar_results}
        for opportunity in company_origin:
            if opportunity.id not in known_ids:
                radar_results.append({
                    "opportunity_id": opportunity.id,
                    "sector_code": opportunity.sector_code,
                    "sector_name": opportunity.title,
                    "signals": [],
                    "evidence_ids": [],
                    "score": opportunity.score,
                    "is_demo": opportunity.is_demo,
                    "origin": opportunity.origin,
                })

        processed = []
        failures = []
        for item in radar_results:
            opportunity = self.session.get(Opportunity, item["opportunity_id"])
            if not opportunity:
                continue
            task = ResearchTask(
                task_type="full_research_cycle",
                subject_type="opportunity",
                subject_id=str(opportunity.id),
                status=TaskStatus.RUNNING.value,
                payload_json=json.dumps(item, ensure_ascii=False, default=str),
                max_attempts=3,
            )
            self.session.add(task)
            self.session.commit()
            self.session.refresh(task)
            try:
                result = self._process(opportunity, task, item)
                task.status = TaskStatus.COMPLETED.value
                task.result_json = json.dumps(result, ensure_ascii=False, default=str)
                processed.append(result)
            except Exception as exc:
                task.status = TaskStatus.FAILED.value
                task.error = str(exc)
                task.attempts += 1
                failures.append({"opportunity_id": opportunity.id, "error": str(exc)})
                self.session.add(SystemAlert(
                    severity="high",
                    alert_type="research_cycle_failed",
                    subject_type="opportunity",
                    subject_id=str(opportunity.id),
                    title=f"研究周期失败：{opportunity.title}",
                    details=str(exc),
                ))
            task.updated_at = datetime.now(timezone.utc)
            self.session.add(task)
            self.session.add(opportunity)
            self.session.commit()

        monitoring = MonitoringService(self.session).review_all()
        prediction_count = EvaluationService(self.session).snapshot_opportunities()
        daily_report = ReportingService(self.session).generate("daily")
        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "radar_count": len(radar_results),
            "processed_count": len(processed),
            "failed_count": len(failures),
            "document_evidence_created": extracted,
            "monitoring": monitoring,
            "prediction_snapshots_created": prediction_count,
            "report_id": daily_report.id,
            "duration_ms": duration_ms,
            "items": processed,
            "failures": failures,
        }

    def _process(self, opportunity: Opportunity, task: ResearchTask, item: dict) -> dict:
        evidence_summary = self.evidence.summary(opportunity.sector_code)
        industry = self._run_agent("industry_researcher", task.id, {
            **item,
            "evidence_summary": self._serialize_evidence_summary(evidence_summary),
        })
        self._advance(opportunity, ResearchStage.INDUSTRY_VALIDATION.value, "产业变化与利润传导完成初步验证")

        links = self.company_analysis.map_companies(opportunity)
        ranking = [{
            "company_id": x.company_id,
            "ranking_score": x.ranking_score,
            "business_purity": x.business_purity,
            "profit_elasticity": x.profit_elasticity,
            "balance_sheet_score": x.balance_sheet_score,
            "cash_quality_score": x.cash_quality_score,
            "valuation_score": x.valuation_score,
        } for x in sorted(links, key=lambda x: x.ranking_score, reverse=True)]
        company_map = self._run_agent("company_mapper", task.id, {
            "opportunity": item,
            "ranking": ranking,
        })
        if links:
            self._advance(opportunity, ResearchStage.COMPANY_MAPPING.value, "完成受益公司量化映射")

        companies = []
        model_gaps = []
        pricing_available = False
        for link in sorted(links, key=lambda x: x.ranking_score, reverse=True)[:5]:
            company = self.session.get(Company, link.company_id)
            tree = self.profit_tree.as_tree(link.company_id)
            model = self.financial.run_company(link.company_id)
            expectation = self.expectation.refresh_company(link.company_id)
            gap = None
            base = model.get("scenarios", {}).get("base")
            if expectation and base and expectation.current_eps > 0:
                modeled_eps_growth = base["eps"] / expectation.current_eps - 1
                gap = modeled_eps_growth - expectation.implied_eps_growth
                model_gaps.append(gap)
                pricing_available = True
            companies.append({
                "company_id": link.company_id,
                "ticker": company.ticker if company else "",
                "name": company.name if company else "",
                "ranking": ranking,
                "profit_tree": tree,
                "financial_model": model,
                "market_expectation": self._model_dict(expectation),
                "model_vs_implied_growth_gap": gap,
            })

        deep_research = self._run_agent("company_researcher", task.id, {
            "opportunity": item,
            "industry": industry,
            "company_map": company_map,
            "companies": companies,
            "evidence_summary": self._serialize_evidence_summary(evidence_summary),
        })
        if links:
            self._advance(opportunity, ResearchStage.DEEP_RESEARCH.value, "利润树、盈利情景与市场预期差完成研究")

        fatal_flags = []
        if evidence_summary["negative"] >= 3:
            fatal_flags.append("multiple_negative_evidence")
        counter = self._run_agent("counter_thesis", task.id, {
            "opportunity": item,
            "industry": industry,
            "company_map": company_map,
            "deep_research": deep_research,
            "evidence_summary": self._serialize_evidence_summary(evidence_summary),
            "fatal_flags": fatal_flags,
        })

        avg_gap = sum(model_gaps) / len(model_gaps) if model_gaps else -1
        decision = self._run_agent("candidate_decider", task.id, {
            "score": opportunity.score,
            "confidence": industry.get("confidence", opportunity.confidence),
            "verified_evidence": evidence_summary["verified"],
            "evidence_paths": evidence_summary["independent_paths"],
            "fatal_risk": counter.get("fatal_risk", False),
            "is_demo": opportunity.is_demo,
            "pricing_available": pricing_available,
            "model_vs_implied_growth_gap": avg_gap,
            "falsification_conditions": industry.get("falsification_conditions", []),
        })

        if decision.get("qualified") and not opportunity.is_demo:
            self._move_if_allowed(opportunity, ResearchStage.CANDIDATE.value, "通过证据、盈利、预期差与反方审查")
        elif decision.get("wait_for_price"):
            self._move_if_allowed(opportunity, ResearchStage.WAITING_PRICE.value, "研究成立但预期差或价格尚不满足")

        opportunity.thesis = industry.get("conclusion", opportunity.thesis)
        opportunity.profit_transmission = industry.get("profit_transmission", opportunity.profit_transmission)
        opportunity.missing_evidence = "; ".join(industry.get("missing_evidence", []))
        opportunity.falsification_conditions = "; ".join(industry.get("falsification_conditions", []))
        opportunity.confidence = float(industry.get("confidence", opportunity.confidence))
        opportunity.market_pricing = (
            f"完成{len(model_gaps)}家公司反向隐含增长测算，平均模型-隐含增速差{avg_gap:.2%}"
            if model_gaps else "缺少可计算的公司市场价格、EPS或盈利模型。"
        )
        opportunity.last_validated_at = datetime.now(timezone.utc)
        self.session.add(opportunity)

        return {
            "opportunity_id": opportunity.id,
            "stage": opportunity.stage,
            "industry": industry,
            "company_map": company_map,
            "companies": companies,
            "deep_research": deep_research,
            "counter": counter,
            "decision": decision,
        }

    def _run_agent(self, role: str, task_id: int, payload: dict) -> dict:
        started = time.perf_counter()
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True).encode()).hexdigest()
        output = {}
        status = "failed"
        error = ""
        try:
            output = analyze_with_retry(self.provider, role, payload, attempts=3)
            status = "completed"
            return output
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            self.session.add(AgentRun(
                role=role,
                provider=self.provider.name,
                model=self.provider.model,
                task_id=task_id,
                input_digest=digest,
                output_json=json.dumps(output, ensure_ascii=False, default=str),
                status=status,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error=error,
            ))
            self.session.commit()

    def _advance(self, opportunity: Opportunity, target: str, reason: str) -> None:
        for step in next_progression_steps(opportunity.stage, target):
            self._move_if_allowed(opportunity, step, reason)

    def _move_if_allowed(self, opportunity: Opportunity, target: str, reason: str) -> None:
        if opportunity.stage == target:
            return
        try:
            validate_transition(opportunity.stage, target)
        except ValueError:
            # A repeated cycle must not move a mature opportunity backwards.
            return
        old = opportunity.stage
        opportunity.stage = target
        opportunity.updated_at = datetime.now(timezone.utc)
        self.session.add(StateTransition(
            opportunity_id=opportunity.id,
            from_stage=old,
            to_stage=target,
            reason=reason,
            actor="orchestrator",
        ))

    @staticmethod
    def _serialize_evidence_summary(summary: dict) -> dict:
        return {k: v for k, v in summary.items() if k != "items"}

    @staticmethod
    def _model_dict(model):
        if model is None:
            return None
        return {column.name: getattr(model, column.name) for column in model.__table__.columns}
