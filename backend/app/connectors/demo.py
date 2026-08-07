from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import random
from pathlib import Path

from .base import (
    CompanyInput,
    CompanySectorMembershipInput,
    CompanySnapshotInput,
    MetricObservationInput,
    SourceDocumentInput,
)


class DemoConnector:
    name = "demo"

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self._sectors = json.loads((self.data_dir / "sectors.json").read_text(encoding="utf-8"))

    def fetch_companies(self) -> list[CompanyInput]:
        raw = json.loads((self.data_dir / "demo_companies.json").read_text(encoding="utf-8"))
        out = [CompanyInput(**x) for x in raw]
        existing = {x.sector_code for x in out}
        # Two synthetic companies per uncovered sector make every industry executable in demo mode.
        for sector in self._sectors:
            if sector["code"] in existing:
                continue
            for idx in range(1, 3):
                out.append(CompanyInput(
                    ticker=f"DEMO{sector['code']}{idx}",
                    name=f"{sector['name']}演示公司{idx}",
                    exchange="DEMO",
                    sector_code=sector["code"],
                    description="Synthetic company used only to exercise full-market research workflows.",
                    market_cap=80 + int(sector["code"]) * 3 + idx * 10,
                    pe=14 + idx * 5,
                    is_demo=True,
                ))
        return out

    def fetch_company_memberships(self) -> list[CompanySectorMembershipInput]:
        companies = self.fetch_companies()
        out = []
        for company in companies:
            out.append(CompanySectorMembershipInput(
                ticker=company.ticker,
                sector_code=company.sector_code,
                relationship_type="primary" if int(company.sector_code) <= 32 else "theme",
                relevance=1.0,
                business_share=0.78 if company.exchange == "DEMO" else 0.65,
                rationale="DEMO primary/theme membership",
                source_name="DEMO taxonomy",
                is_demo=True,
            ))
        return out

    def fetch_company_snapshots(self, since: datetime | None = None) -> list[CompanySnapshotInput]:
        now = datetime(2026, 8, 1, tzinfo=timezone.utc)
        rng = random.Random(20260805)
        hot = {"38", "35", "25", "06", "40"}
        out: list[CompanySnapshotInput] = []
        for cidx, company in enumerate(self.fetch_companies()):
            sector_hot = company.sector_code in hot
            base_revenue = 25 + (cidx % 9) * 6
            shares = 2 + (cidx % 5) * .5
            for i in range(8):
                period = now - timedelta(days=90 * (7 - i))
                growth = (0.05 + i * 0.012) if sector_hot else (0.02 + i * 0.002)
                revenue = base_revenue * ((1 + growth) ** i)
                margin = 0.08 + (0.008 * i if sector_hot else 0.001 * i)
                profit = revenue * margin
                ocf = profit * (0.92 + rng.uniform(-0.08, 0.08))
                price = 10 + cidx * .25 + i * (0.7 if sector_hot else .08)
                eps = profit / shares
                out.append(CompanySnapshotInput(
                    ticker=company.ticker,
                    period=period,
                    revenue=round(revenue, 4),
                    net_profit=round(profit, 4),
                    operating_cash_flow=round(ocf, 4),
                    total_debt=round(revenue * (0.25 if sector_hot else 0.38), 4),
                    net_assets=round(revenue * 0.9, 4),
                    shares=shares,
                    price=round(price, 4),
                    market_cap=round(price * shares, 4),
                    pe=round(price / eps, 3) if eps else None,
                    pb=2.0 + (cidx % 4) * .3,
                    revenue_growth=round(growth, 4),
                    profit_growth=round(growth + (0.06 if sector_hot else 0.005), 4),
                    gross_margin=round(0.25 + (0.025 if sector_hot else 0), 4),
                    net_margin=round(margin, 4),
                    roe=round(0.10 + (0.025 if sector_hot else 0.005), 4),
                    debt_ratio=0.28 if sector_hot else 0.42,
                    order_growth=round((0.12 + i * .018) if sector_hot else (0.03 + i * .002), 4),
                    contract_liability_growth=round((0.10 + i * .015) if sector_hot else 0.02, 4),
                    capacity_utilization=round((0.70 + i * .025) if sector_hot else 0.62, 4),
                    market_share=round(0.08 + (cidx % 3) * .025 + (i * .004 if sector_hot else 0), 4),
                    business_purity=0.82 if sector_hot else 0.66,
                    source_name="DEMO synthetic company dataset",
                    source_url="demo://company-snapshots",
                    is_demo=True,
                ))
        return [x for x in out if since is None or x.period >= since]

    def fetch_metrics(self, since: datetime | None = None) -> list[MetricObservationInput]:
        templates = json.loads((self.data_dir / "metric_templates.json").read_text(encoding="utf-8"))
        now = datetime(2026, 8, 1, tzinfo=timezone.utc)
        rng = random.Random(20260804)
        hot = {"38", "35", "25", "06", "40"}
        observations: list[MetricObservationInput] = []
        for t in templates:
            sector = t["sector_code"]
            base = 100 + rng.random() * 10
            for i in range(12):
                period = now - timedelta(days=30 * (11 - i))
                trend = (i * 1.7 if sector in hot else i * 0.15)
                if t["code"].endswith("inventory_index") and sector in hot:
                    trend = -i * 1.3
                if t["code"].endswith("capacity_utilization") and sector in hot:
                    trend = i * 1.1
                if t["code"].endswith("capex_growth") and sector in hot:
                    trend = i * .9
                value = base + trend + math.sin(i / 2) * 2 + rng.uniform(-1.5, 1.5)
                observations.append(MetricObservationInput(
                    metric_code=t["code"],
                    period=period,
                    value=round(value, 2),
                    source_name=f"DEMO source A {t['code'].split('_', 1)[1]}",
                    source_url="demo://metrics/source-a",
                    credibility=0.3,
                    is_demo=True,
                ))
                if sector in hot:
                    observations.append(MetricObservationInput(
                        metric_code=t["code"],
                        period=period,
                        value=round(value + rng.uniform(-.6, .6), 2),
                        source_name=f"DEMO source B {t['code'].split('_', 1)[1]}",
                        source_url="demo://metrics/source-b",
                        credibility=0.3,
                        is_demo=True,
                    ))
        return [x for x in observations if since is None or x.period >= since]

    def fetch_documents(self, since: datetime | None = None) -> list[SourceDocumentInput]:
        now = datetime(2026, 8, 1, tzinfo=timezone.utc)
        docs = [
            ("38", "电网投资与订单同步改善", "演示资料：电网投资指标与设备订单连续改善，但仍需核实供给扩张和估值。"),
            ("35", "自动化需求回暖", "演示资料：工业自动化需求指数改善，部分公司订单增速回升。"),
            ("25", "半导体设备资本开支变化", "演示资料：资本开支和订单指标改善，但估值处于较高区间。"),
            ("06", "有色金属价差变化", "演示资料：产品原料价差改善，库存压力下降，需警惕供给复产。"),
            ("40", "本地服务需求改善", "演示资料：订单和客流指标改善，需继续验证同店利润和竞争补贴。"),
        ]
        out = []
        for sector, title, text in docs:
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            item = SourceDocumentInput(
                source_type="demo",
                source_name="DEMO research feed",
                title=title,
                source_url=f"demo://document/{sector}",
                published_at=now,
                data_period=now.strftime("%Y-%m"),
                sector_code=sector,
                content_hash=content_hash,
                parsed_text=text,
                credibility=0.3,
                is_demo=True,
            )
            if since is None or item.published_at >= since:
                out.append(item)
        return out
