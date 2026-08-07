"""Generic authenticated JSON connector for licensed providers or internal gateways."""
from datetime import datetime
import httpx

from .base import (
    CompanyInput,
    CompanySectorMembershipInput,
    CompanySnapshotInput,
    MetricObservationInput,
    SourceDocumentInput,
)


class HttpJsonConnector:
    name = "http_json"

    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def _get(self, path: str, since: datetime | None = None) -> list[dict]:
        params = {"since": since.isoformat()} if since else {}
        with httpx.Client(timeout=60, headers=self.headers) as client:
            response = client.get(f"{self.base_url}/{path}", params=params)
            if response.status_code == 404:
                return []
            return response.raise_for_status().json()

    def fetch_companies(self) -> list[CompanyInput]:
        return [CompanyInput(**row) for row in self._get("companies")]

    def fetch_company_memberships(self) -> list[CompanySectorMembershipInput]:
        return [CompanySectorMembershipInput(**row) for row in self._get("company-memberships")]

    def fetch_company_snapshots(self, since: datetime | None = None) -> list[CompanySnapshotInput]:
        return [CompanySnapshotInput(**row) for row in self._get("company-snapshots", since)]

    def fetch_metrics(self, since: datetime | None = None) -> list[MetricObservationInput]:
        return [MetricObservationInput(**row) for row in self._get("metrics", since)]

    def fetch_documents(self, since: datetime | None = None) -> list[SourceDocumentInput]:
        return [SourceDocumentInput(**row) for row in self._get("documents", since)]
