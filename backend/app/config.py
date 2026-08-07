from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Investment Research OS"
    environment: str = "development"
    database_url: str = "sqlite:///./investment_os.db"
    cors_origins: str = "http://localhost:3000,http://localhost:8000"
    model_provider: str = "heuristic"
    openai_api_key: str | None = None
    openai_model: str = ""
    anthropic_api_key: str | None = None
    anthropic_model: str = ""
    research_cycle_minutes: int = 60
    auto_seed: bool = True
    demo_mode: bool = True
    api_base_url: str = "http://localhost:8000"
    tushare_token: str | None = None
    tushare_api_url: str = "http://api.tushare.pro"
    data_provider: str = "akshare"  # "akshare" (free) or "tushare" (paid, needs token)
    akshare_report_date: str = ""  # YYYYMMDD report period for earnings forecasts; empty=auto
    akshare_forecast_min_pre: float = 50.0  # % pre-increase threshold to trigger financial deep-dive
    akshare_forecast_max_pre: float = -10.0  # % pre-decrease threshold to trigger financial deep-dive
    akshare_max_deep_dive: int = 1656  # cap on companies deep-dived per sync (full trigger set)
    baostock_trade_date: str = ""  # YYYY-MM-DD for valuation snapshots; empty=today
    real_data_sync_enabled: bool = False
    real_data_sync_minutes: int = 60
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
