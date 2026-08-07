# Investment Research OS — Codex Rules

## Goal
Build and maintain a full-market, evidence-first investment research operating system. Never narrow the product to a few hard-coded sectors. Sector-specific behavior must be implemented as data-driven templates or connectors.

## Required checks
Before declaring a change complete:
1. Run backend tests.
2. Run `node --check frontend/app.js` when frontend JavaScript changes; the frontend has no package build step.
3. Preserve source provenance, data-period timestamps and audit history.
4. Do not add automatic trading or broker order execution.
5. Demo data must remain clearly labeled as demo.

## Architecture
- `backend/app/models.py`: persistent domain model.
- `backend/app/services/`: deterministic research logic.
- `backend/app/agents/`: model adapters and structured research roles.
- `backend/app/connectors/`: pluggable data sources.
- `backend/app/mcp_server.py`: common tool surface for Codex and Claude.
- `frontend/`: research dashboard only; it does not own business logic.

## Engineering rules
- Use deterministic code for arithmetic, scoring, state transitions and anomaly detection.
- Use LLMs for extraction, hypothesis generation, cross-document reasoning and adversarial review.
- Every AI conclusion must carry evidence IDs, confidence, missing evidence and falsification conditions.
- Never overwrite historical assumptions or state transitions; append revisions.
- Avoid vendor lock-in. OpenAI, Anthropic and heuristic providers implement the same interface.
