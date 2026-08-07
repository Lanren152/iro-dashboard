import json
import os
import httpx

from mcp.server.fastmcp import FastMCP
from .config import get_settings

API = os.getenv("API_BASE_URL", get_settings().api_base_url).rstrip("/")
mcp = FastMCP(
    "Investment Research OS",
    instructions=(
        "Evidence-first full-market research system. Demo records are synthetic. "
        "Preserve provenance, distinguish facts from inference, and never execute trades."
    ),
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    port=8001,
)


def call(method: str, path: str, payload: dict | None = None):
    with httpx.Client(timeout=180) as client:
        response = client.request(method, f"{API}{path}", json=payload)
        response.raise_for_status()
        return response.json()


@mcp.tool()
def get_dashboard_summary() -> dict:
    """Return market coverage, opportunities, alerts, tasks, reports and agent runs."""
    return call("GET", "/api/dashboard")


@mcp.tool()
def run_market_scan() -> dict:
    """Run deterministic anomaly detection across every configured sector and metric."""
    return call("POST", "/api/research/run-scan")


@mcp.tool()
def run_research_cycle() -> dict:
    """Run full market/company discovery, evidence, mapping, modeling, counter-thesis and monitoring."""
    return call("POST", "/api/research/run-cycle")


@mcp.tool()
def run_logic_monitoring() -> dict:
    """Review mature opportunities for weakening evidence and create exception alerts."""
    return call("POST", "/api/research/run-monitoring")


@mcp.tool()
def list_opportunities(stage: str | None = None, origin: str | None = None, limit: int = 50) -> list[dict]:
    query = [f"limit={limit}"]
    if stage:
        query.append(f"stage={stage}")
    if origin:
        query.append(f"origin={origin}")
    return call("GET", f"/api/opportunities?{'&'.join(query)}")


@mcp.tool()
def get_opportunity_detail(opportunity_id: int) -> dict:
    """Read thesis, ranked companies, evidence, expectations, state history, tasks and predictions."""
    return call("GET", f"/api/opportunities/{opportunity_id}")


@mcp.tool()
def get_sector_detail(sector_code: str) -> dict:
    """Read sector metrics, mapped companies, evidence and opportunities."""
    return call("GET", f"/api/sectors/{sector_code}")


@mcp.tool()
def search_companies(query: str = "", sector_code: str | None = None, limit: int = 100) -> list[dict]:
    params = [f"limit={limit}"]
    if query:
        params.append(f"q={query}")
    if sector_code:
        params.append(f"sector_code={sector_code}")
    return call("GET", f"/api/companies?{'&'.join(params)}")


@mcp.tool()
def get_company_research(company_id: int) -> dict:
    """Read company snapshots, memberships, profit tree, scenarios, expectations and evidence."""
    return call("GET", f"/api/companies/{company_id}")


@mcp.tool()
def compare_company_peers(company_id: int) -> list[dict]:
    """Compare the company with peers sharing primary or thematic sector memberships."""
    return call("GET", f"/api/companies/{company_id}/peers")


@mcp.tool()
def get_profit_driver_tree(company_id: int) -> list[dict]:
    """Return the persistent profit-driver tree for a company."""
    return call("GET", f"/api/companies/{company_id}/profit-tree")


@mcp.tool()
def get_company_financial_model(company_id: int, period: str = "next_year") -> dict:
    """Run bear/base/bull deterministic company scenarios from versioned assumptions."""
    return call("GET", f"/api/companies/{company_id}/financial-model?period={period}")


@mcp.tool()
def update_profit_assumption(
    company_id: int,
    variable: str,
    scenario: str,
    value: float,
    period: str = "next_year",
    unit: str = "",
    rationale: str = "",
    evidence_ids: list[int] = [],
    opportunity_id: int | None = None,
) -> dict:
    """Append a versioned, evidence-linked profit assumption without overwriting history."""
    return call("POST", f"/api/companies/{company_id}/assumptions", {
        "variable": variable,
        "scenario": scenario,
        "period": period,
        "value": value,
        "unit": unit,
        "rationale": rationale,
        "evidence_ids": evidence_ids,
        "opportunity_id": opportunity_id,
    })


@mcp.tool()
def search_evidence(
    query: str = "",
    sector_code: str | None = None,
    company_id: int | None = None,
    verified: bool | None = None,
    limit: int = 100,
) -> list[dict]:
    params = [f"limit={limit}"]
    if query:
        params.append(f"q={query}")
    if sector_code:
        params.append(f"sector_code={sector_code}")
    if company_id is not None:
        params.append(f"company_id={company_id}")
    if verified is not None:
        params.append(f"verified={str(verified).lower()}")
    return call("GET", f"/api/evidence?{'&'.join(params)}")


@mcp.tool()
def search_source_documents(
    query: str = "",
    source_type: str | None = None,
    sector_code: str | None = None,
    company_id: int | None = None,
    limit: int = 100,
) -> list[dict]:
    params = [f"limit={limit}"]
    if query:
        params.append(f"q={query}")
    if source_type:
        params.append(f"source_type={source_type}")
    if sector_code:
        params.append(f"sector_code={sector_code}")
    if company_id is not None:
        params.append(f"company_id={company_id}")
    return call("GET", f"/api/documents?{'&'.join(params)}")


@mcp.tool()
def read_source_document(document_id: int) -> dict:
    """Read the preserved source text and evidence extracted from it."""
    return call("GET", f"/api/documents/{document_id}")


@mcp.tool()
def get_pending_exceptions(limit: int = 100) -> list[dict]:
    """Return only open alerts requiring review or data repair."""
    return call("GET", f"/api/alerts?status=open&limit={limit}")


@mcp.tool()
def get_research_reports(cadence: str | None = None, limit: int = 20) -> list[dict]:
    suffix = f"?limit={limit}" + (f"&cadence={cadence}" if cadence else "")
    return call("GET", f"/api/reports{suffix}")


@mcp.tool()
def create_hypothesis(
    title: str,
    sector_code: str,
    thesis: str,
    missing_evidence: list[str],
    falsification_conditions: list[str],
    evidence_ids: list[int] = [],
    origin_company_id: int | None = None,
) -> dict:
    """Persist a manual or company-origin research hypothesis in watch state."""
    return call("POST", "/api/hypotheses", {
        "title": title,
        "sector_code": sector_code,
        "thesis": thesis,
        "origin_company_id": origin_company_id,
        "missing_evidence": missing_evidence,
        "falsification_conditions": falsification_conditions,
        "evidence_ids": evidence_ids,
    })


@mcp.tool()
def change_research_state(opportunity_id: int, stage: str, reason: str, actor: str = "mcp_agent") -> dict:
    """Move an opportunity through the audited research state machine."""
    return call("POST", f"/api/opportunities/{opportunity_id}/state", {
        "stage": stage,
        "reason": reason,
        "actor": actor,
    })


@mcp.tool()
def run_financial_scenario(
    volume: float,
    price: float,
    unit_cost: float,
    fixed_cost: float,
    tax_rate: float,
    shares: float,
    valuation_multiple: float,
) -> dict:
    """Run deterministic profit, EPS and valuation arithmetic from explicit assumptions."""
    return call("POST", "/api/financial/scenario", {
        "volume": volume,
        "price": price,
        "unit_cost": unit_cost,
        "fixed_cost": fixed_cost,
        "tax_rate": tax_rate,
        "shares": shares,
        "valuation_multiple": valuation_multiple,
    })


@mcp.tool()
def calculate_market_implied_growth(
    price: float,
    current_eps: float,
    exit_pe: float = 20,
    years: int = 3,
    required_return: float = .15,
) -> dict:
    """Reverse-calculate EPS growth required by the current price and return hurdle."""
    return call("POST", "/api/financial/reverse-expectation", {
        "price": price,
        "current_eps": current_eps,
        "exit_pe": exit_pe,
        "years": years,
        "required_return": required_return,
    })


@mcp.resource("investment://system/instructions")
def system_instructions() -> str:
    return json.dumps({
        "principles": [
            "full-market and company-driven discovery",
            "evidence before interpretation",
            "source and data-period provenance",
            "independent evidence verification",
            "profit-tree and scenario modeling",
            "market-implied expectation comparison",
            "explicit counter-thesis and falsification",
            "no order execution",
            "demo data is never a real recommendation",
        ]
    }, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
