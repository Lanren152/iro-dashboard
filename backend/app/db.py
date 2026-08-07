from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session as SASession, sessionmaker
from .config import get_settings

class Base(DeclarativeBase):
    pass

class AppSession(SASession):
    """Compatibility helper: scalar ORM selects expose .all()/.first() like SQLModel."""
    def exec(self, statement):
        return self.execute(statement).scalars()

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, class_=AppSession, expire_on_commit=False)

def init_db() -> None:
    from . import models  # noqa: F401
    Base.metadata.create_all(engine)

def get_session():
    with SessionLocal() as session:
        yield session
