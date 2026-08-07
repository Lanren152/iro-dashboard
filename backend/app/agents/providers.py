from abc import ABC, abstractmethod
import json
import time

from ..config import get_settings


ROLE_REQUIRED_FIELDS = {
    "industry_researcher": {"conclusion", "confidence", "missing_evidence", "falsification_conditions"},
    "company_mapper": {"mapped_company_count", "confidence"},
    "company_researcher": {"conclusion", "confidence", "missing_evidence"},
    "counter_thesis": {"counterarguments", "fatal_risk", "confidence"},
    "candidate_decider": {"qualified", "wait_for_price", "reason", "confidence"},
}


class ResearchProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def analyze(self, role: str, payload: dict) -> dict: ...


class HeuristicProvider(ResearchProvider):
    name = "heuristic"
    model = "deterministic-v2"

    def analyze(self, role: str, payload: dict) -> dict:
        if role == "industry_researcher":
            signals = payload.get("signals", [])
            verified = int(payload.get("evidence_summary", {}).get("verified", 0))
            return {
                "conclusion": "多项行业指标同步变化，利润传导具有初步证据。" if len(signals) >= 2 else "证据不足，继续观察。",
                "confidence": min(.88, .42 + len(signals) * .06 + verified * .04),
                "profit_transmission": "需求/订单→销量，价差/利用率→单位利润，现金流验证增长质量。",
                "missing_evidence": ["真实供给扩张", "竞争格局", "公司业务纯度", "市场隐含预期"],
                "counterarguments": ["可能是季节性或补库存", "供给扩张可能吞噬利润"],
                "falsification_conditions": ["关键指标连续两个周期反向", "供给增速显著超过需求增速"],
                "evidence_ids": payload.get("evidence_ids", []),
            }
        if role == "company_mapper":
            ranking = payload.get("ranking", [])
            return {
                "ranking_method": "业务纯度、利润弹性、资产负债表、现金质量和估值",
                "mapped_company_count": len(ranking),
                "top_company_ids": [x["company_id"] for x in ranking[:5]],
                "confidence": .76 if ranking else .25,
                "missing_evidence": [] if ranking else ["公司业务分部与财务数据"],
                "counterarguments": ["行业受益不代表公司能获得利润"],
                "falsification_conditions": ["相关业务占比过低", "产能或客户无法兑现"],
            }
        if role == "company_researcher":
            company_results = payload.get("companies", [])
            verified = payload.get("evidence_summary", {}).get("verified", 0)
            return {
                "conclusion": "已完成公司利润树、三情景盈利模型和市场隐含预期比较。",
                "company_count": len(company_results),
                "confidence": min(.85, .5 + len(company_results) * .025 + verified * .025),
                "missing_evidence": ["管理层诚信与资本配置", "客户/供应商交叉验证"],
                "counterarguments": ["盈利模型对销量、成本与估值倍数敏感"],
                "falsification_conditions": ["基准情景低于市场隐含增长", "现金流持续落后利润"],
            }
        if role == "counter_thesis":
            negative = payload.get("evidence_summary", {}).get("negative", 0)
            fatal = bool(payload.get("fatal_flags")) or negative >= 3
            return {
                "counterarguments": [
                    "需求变化可能只是短周期补库存",
                    "新增供给可能压低价格和利润率",
                    "业务纯度或产能兑现可能低于预期",
                    "估值可能已经反映乐观情景",
                ],
                "fatal_risk": fatal,
                "confidence": .72,
                "missing_evidence": ["最强竞争对手成本曲线", "客户集中度和替代风险"],
                "falsification_conditions": ["出现经验证的治理风险", "悲观情景仍高于当前定价的假设被推翻"],
            }
        if role == "candidate_decider":
            score = float(payload.get("score", 0))
            fatal = bool(payload.get("fatal_risk"))
            demo = bool(payload.get("is_demo"))
            pricing = bool(payload.get("pricing_available"))
            verified = int(payload.get("verified_evidence", 0))
            paths = int(payload.get("evidence_paths", 0))
            model_gap = float(payload.get("model_vs_implied_growth_gap", -1))
            qualified = score >= 72 and verified >= 2 and paths >= 2 and not fatal and pricing and model_gap > .03 and not demo
            wait = score >= 65 and paths >= 2 and not fatal and (not pricing or model_gap <= .03) and not demo
            return {
                "qualified": qualified,
                "wait_for_price": wait,
                "reason": "候选必须同时通过真实证据、公司盈利模型、市场隐含预期和反方审查。",
                "confidence": .82,
                "missing_evidence": [] if qualified else ["仍未满足全部候选硬门槛"],
                "counterarguments": [],
                "falsification_conditions": payload.get("falsification_conditions", []),
            }
        return {
            "conclusion": "已按离线规则处理",
            "confidence": .5,
            "missing_evidence": [],
            "counterarguments": [],
            "falsification_conditions": [],
        }


class OpenAIProvider(ResearchProvider):
    name = "openai"

    def __init__(self):
        from openai import OpenAI
        s = get_settings()
        if not s.openai_api_key or not s.openai_model:
            raise RuntimeError("OPENAI_API_KEY and OPENAI_MODEL must be configured")
        self.client = OpenAI(api_key=s.openai_api_key)
        self.model = s.openai_model

    def analyze(self, role: str, payload: dict) -> dict:
        response = self.client.responses.create(model=self.model, input=_prompt(role, payload))
        return _validate(role, _parse_json(response.output_text))


class AnthropicProvider(ResearchProvider):
    name = "anthropic"

    def __init__(self):
        import anthropic
        s = get_settings()
        if not s.anthropic_api_key or not s.anthropic_model:
            raise RuntimeError("ANTHROPIC_API_KEY and ANTHROPIC_MODEL must be configured")
        self.client = anthropic.Anthropic(api_key=s.anthropic_api_key)
        self.model = s.anthropic_model

    def analyze(self, role: str, payload: dict) -> dict:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=2400,
            messages=[{"role": "user", "content": _prompt(role, payload)}],
        )
        text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
        return _validate(role, _parse_json(text))


class DualReviewProvider(ResearchProvider):
    name = "dual"
    model = "openai+anthropic"

    def __init__(self):
        self.primary = OpenAIProvider()
        self.reviewer = AnthropicProvider()

    def analyze(self, role: str, payload: dict) -> dict:
        primary = self.primary.analyze(role, payload)
        review = self.reviewer.analyze("counter_thesis", {"primary": primary, "source_payload": payload})
        merged = dict(primary)
        merged["independent_review"] = review
        merged["confidence"] = min(float(primary.get("confidence", .5)), float(review.get("confidence", .5)))
        if review.get("fatal_risk"):
            merged["fatal_risk"] = True
        return _validate(role, merged)


def analyze_with_retry(provider: ResearchProvider, role: str, payload: dict, attempts: int = 3) -> dict:
    error = None
    for attempt in range(1, attempts + 1):
        try:
            return _validate(role, provider.analyze(role, payload))
        except Exception as exc:
            error = exc
            if attempt < attempts:
                time.sleep(.15 * attempt)
    raise RuntimeError(f"{role} failed after {attempts} attempts: {error}")


def _prompt(role: str, payload: dict) -> str:
    return f"""You are the {role} in an evidence-first full-market investment research system.
Return one valid JSON object only. Distinguish facts from inference. Include confidence from 0 to 1,
missing_evidence, counterarguments, falsification_conditions, and referenced evidence_ids where available.
Do not recommend or execute a trade. Do not treat media volume or price momentum as business evidence.
Payload:\n{json.dumps(payload, ensure_ascii=False, default=str)}"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


def _validate(role: str, output: dict) -> dict:
    if not isinstance(output, dict):
        raise ValueError("Agent output must be a JSON object")
    missing = ROLE_REQUIRED_FIELDS.get(role, set()) - set(output)
    if missing:
        raise ValueError(f"Agent output missing fields for {role}: {sorted(missing)}")
    confidence = float(output.get("confidence", .5))
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    output["confidence"] = confidence
    return output


def get_provider() -> ResearchProvider:
    name = get_settings().model_provider.lower()
    if name == "openai":
        return OpenAIProvider()
    if name == "anthropic":
        return AnthropicProvider()
    if name == "dual":
        return DualReviewProvider()
    return HeuristicProvider()
