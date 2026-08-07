import logging
import time
from datetime import datetime, timezone

from .db import AppSession as Session, engine, init_db
from .config import get_settings
from .seed import seed_all, seed_taxonomy
from .agents.orchestrator import ResearchOrchestrator
from .services.real_data import sync_tushare

logging.basicConfig(level=logging.INFO)


def run_research_cycle():
    with Session(engine) as session:
        result = ResearchOrchestrator(session).run_cycle()
        logging.info("research cycle: %s", result)


def run_data_sync(include_master: bool):
    with Session(engine) as session:
        result = sync_tushare(session, include_master=include_master)
        logging.info("real data sync: %s", result)


def main():
    init_db()
    settings = get_settings()
    if settings.auto_seed:
        seed_all() if settings.demo_mode else seed_taxonomy()
    research_interval = max(1, settings.research_cycle_minutes) * 60
    data_interval = max(1, settings.real_data_sync_minutes) * 60
    last_research = 0.0
    last_data = 0.0
    last_master_day = None

    while True:
        now = time.monotonic()
        utc_day = datetime.now(timezone.utc).date().isoformat()
        if settings.real_data_sync_enabled and now - last_data >= data_interval:
            try:
                include_master = last_master_day != utc_day
                run_data_sync(include_master=include_master)
                last_data = now
                if include_master:
                    last_master_day = utc_day
            except Exception:
                logging.exception("real data sync failed")
        if now - last_research >= research_interval:
            try:
                run_research_cycle()
            except Exception:
                logging.exception("research cycle failed")
            last_research = now
        time.sleep(15)


if __name__ == "__main__":
    main()
