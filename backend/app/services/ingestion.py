from sqlalchemy import select

from ..db import AppSession as Session
from ..connectors.base import DataConnector
from ..models import (
    Company,
    CompanySectorMembership,
    CompanySnapshot,
    MetricObservation,
    SourceDocument,
)


class IngestionService:
    def __init__(self, session: Session):
        self.session = session

    def ingest(self, connector: DataConnector) -> dict:
        counts = {"companies": 0, "memberships": 0, "company_snapshots": 0, "metrics": 0, "documents": 0}
        for row in connector.fetch_companies():
            existing = self.session.exec(select(Company).where(Company.ticker == row.ticker)).first()
            if not existing:
                self.session.add(Company(**row.model_dump()))
                counts["companies"] += 1
            else:
                for key, value in row.model_dump().items():
                    setattr(existing, key, value)
                self.session.add(existing)
        self.session.commit()

        membership_fetcher = getattr(connector, "fetch_company_memberships", lambda: [])
        for row in membership_fetcher():
            company = self.session.exec(select(Company).where(Company.ticker == row.ticker)).first()
            if not company:
                continue
            exists = self.session.exec(select(CompanySectorMembership).where(
                CompanySectorMembership.company_id == company.id,
                CompanySectorMembership.sector_code == row.sector_code,
                CompanySectorMembership.relationship_type == row.relationship_type,
            )).first()
            payload = row.model_dump(exclude={"ticker"}) | {"company_id": company.id}
            if not exists:
                self.session.add(CompanySectorMembership(**payload))
                counts["memberships"] += 1
            else:
                for key, value in payload.items():
                    setattr(exists, key, value)
                self.session.add(exists)
        self.session.commit()

        snapshot_fetcher = getattr(connector, "fetch_company_snapshots", lambda since=None: [])
        for row in snapshot_fetcher():
            company = self.session.exec(select(Company).where(Company.ticker == row.ticker)).first()
            if not company:
                continue
            exists = self.session.exec(select(CompanySnapshot).where(
                CompanySnapshot.company_id == company.id,
                CompanySnapshot.period == row.period,
                CompanySnapshot.source_name == row.source_name,
                CompanySnapshot.version_key == row.version_key,
            )).first()
            payload = row.model_dump(exclude={"ticker"}) | {"company_id": company.id}
            if not exists:
                self.session.add(CompanySnapshot(**payload))
                counts["company_snapshots"] += 1
            else:
                for key, value in payload.items():
                    setattr(exists, key, value)
                self.session.add(exists)
        self.session.commit()

        for row in connector.fetch_metrics():
            exists = self.session.exec(select(MetricObservation).where(
                MetricObservation.metric_code == row.metric_code,
                MetricObservation.period == row.period,
                MetricObservation.source_name == row.source_name,
            )).first()
            if not exists:
                self.session.add(MetricObservation(**row.model_dump()))
                counts["metrics"] += 1
        self.session.commit()

        for row in connector.fetch_documents():
            exists = self.session.exec(select(SourceDocument).where(SourceDocument.content_hash == row.content_hash)).first()
            if exists:
                continue
            company_id = None
            if row.company_ticker:
                company = self.session.exec(select(Company).where(Company.ticker == row.company_ticker)).first()
                company_id = company.id if company else None
            payload = row.model_dump(exclude={"company_ticker"}) | {"company_id": company_id}
            self.session.add(SourceDocument(**payload))
            counts["documents"] += 1
        self.session.commit()
        return counts
