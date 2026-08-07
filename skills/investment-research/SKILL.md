---
name: investment-research
description: Run evidence-first full-market and company-driven research through the Investment Research OS MCP tools.
---

# Full-market investment research workflow

1. Call `get_dashboard_summary` first. Review open exceptions, stale evidence and recent state changes.
2. Use `run_market_scan` for deterministic sector anomalies. Do not equate media attention or price momentum with business evidence.
3. Use `run_research_cycle` to combine market-driven and company-driven discovery, industry validation, company mapping, profit modeling, implied expectation analysis and counter-thesis review.
4. Inspect opportunities with `get_opportunity_detail`; verify source rank, data period, independent path and falsification conditions.
5. Use `search_source_documents` and `read_source_document` to return to original material. AI summaries never replace source text.
6. Use `search_companies`, `compare_company_peers` and `get_company_research` before making a company-level conclusion.
7. Read `get_profit_driver_tree`; modify a forecast only through `update_profit_assumption`, with rationale and evidence IDs. Never overwrite past assumptions.
8. Use `get_company_financial_model` for bear/base/bull scenarios and `calculate_market_implied_growth` for current-price expectations.
9. Require independent counter-thesis review before candidate status. A high-quality company is not automatically an attractive stock.
10. Persist conclusions through `create_hypothesis` and `change_research_state`; do not leave persistent research only in chat.
11. Use `get_pending_exceptions` and `get_research_reports` to minimize human intervention.
12. Treat every DEMO record as synthetic and return “no qualified live opportunity” when real evidence thresholds are not met.
13. Never execute or suggest an automatic broker order.
