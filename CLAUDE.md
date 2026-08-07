# Investment Research OS — Claude Code Instructions

This repository implements a full-market investment research system. Treat the database, evidence graph and state machine as the source of truth; never rely on chat memory for persistent research state.

When changing research logic, keep the workflow market-wide and data-driven. Do not solve requests by hard-coding a small list of sectors or companies. Arithmetic and state transitions belong in deterministic Python. Language models are used for document reasoning, hypothesis formation and counter-thesis review.

Before finishing, run `make test`; for frontend JavaScript changes also run `node --check frontend/app.js`. Never add live order execution. Preserve provenance, timestamps and append-only audit records.
