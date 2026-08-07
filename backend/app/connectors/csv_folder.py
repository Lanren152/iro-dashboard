"""Zero-code connector for licensed exports and manually curated datasets.

Supported files:
- companies.csv
- company_memberships.csv
- company_snapshots.csv
- metrics.csv
- documents.jsonl
"""
from datetime import datetime
import csv
import json
from pathlib import Path

from .base import (
    CompanyInput,
    CompanySectorMembershipInput,
    CompanySnapshotInput,
    MetricObservationInput,
    SourceDocumentInput,
)


def _bool(value) -> bool:
    return str(value or "false").lower() in {"1", "true", "yes"}


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _float_or_none(value):
    return float(value) if value not in (None, "") else None


class CsvFolderConnector:
    name = "csv_folder"

    def __init__(self, folder: str):
        self.folder = Path(folder)
        if not self.folder.exists():
            raise FileNotFoundError(folder)

    def _rows(self, filename: str) -> list[dict]:
        path = self.folder / filename
        if not path.exists():
            return []
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def fetch_companies(self) -> list[CompanyInput]:
        out = []
        for row in self._rows("companies.csv"):
            for key in ("market_cap", "pe"):
                row[key] = _float_or_none(row.get(key))
            row["is_demo"] = _bool(row.get("is_demo"))
            out.append(CompanyInput(**row))
        return out

    def fetch_company_memberships(self) -> list[CompanySectorMembershipInput]:
        out = []
        for row in self._rows("company_memberships.csv"):
            row["relevance"] = float(row.get("relevance") or 1)
            row["business_share"] = float(row.get("business_share") or 1)
            row["is_demo"] = _bool(row.get("is_demo"))
            out.append(CompanySectorMembershipInput(**row))
        return out

    def fetch_company_snapshots(self, since: datetime | None = None) -> list[CompanySnapshotInput]:
        numeric = {
            "revenue", "net_profit", "operating_cash_flow", "total_debt", "net_assets", "shares",
            "price", "market_cap", "pe", "pb", "revenue_growth", "profit_growth", "gross_margin",
            "net_margin", "roe", "debt_ratio", "order_growth", "contract_liability_growth",
            "capacity_utilization", "market_share", "business_purity",
        }
        out = []
        for row in self._rows("company_snapshots.csv"):
            row["period"] = _dt(row["period"])
            row["data_kind"] = row.get("data_kind") or "composite"
            row["version_key"] = row.get("version_key") or ""
            for key in numeric:
                row[key] = _float_or_none(row.get(key))
            row["is_demo"] = _bool(row.get("is_demo"))
            item = CompanySnapshotInput(**row)
            if since is None or item.period >= since:
                out.append(item)
        return out

    def fetch_metrics(self, since: datetime | None = None) -> list[MetricObservationInput]:
        out = []
        for row in self._rows("metrics.csv"):
            row["period"] = _dt(row["period"])
            row["value"] = float(row["value"])
            row["credibility"] = float(row.get("credibility") or .5)
            row["is_demo"] = _bool(row.get("is_demo"))
            item = MetricObservationInput(**row)
            if since is None or item.period >= since:
                out.append(item)
        return out

    def fetch_documents(self, since: datetime | None = None) -> list[SourceDocumentInput]:
        path = self.folder / "documents.jsonl"
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row["published_at"] = _dt(row["published_at"])
            item = SourceDocumentInput(**row)
            if since is None or item.published_at >= since:
                out.append(item)
        return out
