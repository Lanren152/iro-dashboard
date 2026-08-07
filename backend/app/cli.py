import argparse, json
from .db import init_db, SessionLocal
from .seed import seed_all, seed_taxonomy
from .agents.orchestrator import ResearchOrchestrator
from .connectors.csv_folder import CsvFolderConnector
from .connectors.http_json import HttpJsonConnector
from .services.ingestion import IngestionService
from .services.real_data import sync_akshare, sync_tushare, sync_valuation


def main():
    parser = argparse.ArgumentParser(prog="investment-os")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed")
    sub.add_parser("init-taxonomy")
    sub.add_parser("run-cycle")

    ingest = sub.add_parser("ingest-csv")
    ingest.add_argument("folder")

    http = sub.add_parser("ingest-http")
    http.add_argument("base_url")
    http.add_argument("--token", default=None)

    ts = sub.add_parser("sync-tushare")
    ts.add_argument("--trade-date", help="YYYYMMDD; omitted means latest open trade date")
    ts.add_argument("--announcement-date", help="YYYYMMDD; omitted means current UTC date")
    ts.add_argument("--skip-master", action="store_true", help="skip security master and industry membership")

    ak = sub.add_parser("sync-akshare", help="sync free akshare data (no token required)")
    ak.add_argument("--report-date", help="YYYYMMDD report period for earnings forecasts; omitted means auto")
    ak.add_argument("--skip-master", action="store_true", help="skip security master and industry membership")
    ak.add_argument("--skip-deep-dive", action="store_true", help="only ingest forecast signals, no financial deep-dive")
    ak.add_argument("--max-deep-dive", type=int, default=None, help="cap on companies deep-dived per sync")

    val = sub.add_parser("sync-valuation", help="sync baostock financials + valuation (no token required)")
    val.add_argument("--report-date", help="YYYYMMDD report period for earnings forecasts; omitted means auto")
    val.add_argument("--trade-date", help="YYYY-MM-DD trade date for valuation; omitted means today")
    val.add_argument("--max-tickers", type=int, default=None, help="cap on companies pulled per sync")

    args = parser.parse_args()
    init_db()
    if args.command == "seed":
        result = seed_all()
    elif args.command == "init-taxonomy":
        result = seed_taxonomy()
    elif args.command == "run-cycle":
        with SessionLocal() as session:
            result = ResearchOrchestrator(session).run_cycle()
    elif args.command == "ingest-csv":
        with SessionLocal() as session:
            result = IngestionService(session).ingest(CsvFolderConnector(args.folder))
    elif args.command == "ingest-http":
        with SessionLocal() as session:
            result = IngestionService(session).ingest(HttpJsonConnector(args.base_url, args.token))
    elif args.command == "sync-akshare":
        with SessionLocal() as session:
            result = sync_akshare(
                session,
                report_date=args.report_date,
                include_master=not args.skip_master,
                include_deep_dive=not args.skip_deep_dive,
                max_deep_dive=args.max_deep_dive,
            )
    elif args.command == "sync-valuation":
        with SessionLocal() as session:
            result = sync_valuation(
                session,
                report_date=args.report_date,
                trade_date=args.trade_date,
                max_tickers=args.max_tickers,
            )
    else:
        with SessionLocal() as session:
            result = sync_tushare(
                session,
                trade_date=args.trade_date,
                announcement_date=args.announcement_date,
                include_master=not args.skip_master,
            )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
