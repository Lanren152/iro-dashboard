import json
from pathlib import Path
from sqlalchemy import select

from .db import AppSession as Session
from .db import engine, init_db
from .models import MetricDefinition, Sector
from .connectors.demo import DemoConnector
from .services.ingestion import IngestionService

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
if not DATA_DIR.exists():
    DATA_DIR = Path("data")


def _signal_role(code: str) -> str:
    if code.endswith(("demand_index", "order_growth", "capex_growth")):
        return "leading"
    if code.endswith(("price_spread", "capacity_utilization")):
        return "confirming"
    return "risk"


def seed_taxonomy() -> dict:
    """Initialize sector and metric definitions without inserting demo companies."""
    init_db()
    with Session(engine) as session:
        sector_count = 0
        metric_count = 0
        for row in json.loads((DATA_DIR / "sectors.json").read_text(encoding="utf-8")):
            if not session.get(Sector, row["code"]):
                session.add(Sector(**row))
                sector_count += 1
        session.commit()
        for row in json.loads((DATA_DIR / "metric_templates.json").read_text(encoding="utf-8")):
            if not session.exec(select(MetricDefinition).where(MetricDefinition.code == row["code"])).first():
                session.add(MetricDefinition(**row, signal_role=_signal_role(row["code"])))
                metric_count += 1
        session.commit()
        return {"sectors": sector_count, "metric_definitions": metric_count}


def seed_all() -> dict:
    counts = seed_taxonomy()
    with Session(engine) as session:
        ingested = IngestionService(session).ingest(DemoConnector(str(DATA_DIR)))
        return {**counts, **ingested}


if __name__ == "__main__":
    print(seed_all())
