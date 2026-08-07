"""Tests for the baostock connector (financials + valuation).

The connector talks to baostock's login/query functions; the tests replace
those with deterministic fakes so the field mapping is verified offline.
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_baostock_connector.db"
os.environ["AUTO_SEED"] = "false"

from app.connectors.baostock import BaostockConnector, _quarter_ago, _to_bs_code


class FakeRowSet:
    def __init__(self, rows):
        self._rows = rows or []
        self._i = 0
        self.error_code = "0"

    def next(self):
        if self._i < len(self._rows):
            return True
        return False

    def get_row_data(self):
        row = self._rows[self._i]
        self._i += 1
        return row


class FakeBaostock:
    login_calls = 0
    logout_calls = 0

    @staticmethod
    def login():
        FakeBaostock.login_calls += 1
        return type("R", (), {"error_code": "0", "error_msg": ""})()

    @staticmethod
    def logout():
        FakeBaostock.logout_calls += 1

    @staticmethod
    def query_history_k_data_plus(code, fields, start_date, end_date, frequency, adjustflag):
        quotes = {
            "sh.600519": [["2026-08-07", "1309.2200", "19.786372", "6.041594", "0"]],
            "sz.300750": [["2026-08-07", "388.0700", "21.123093", "4.732960", "0"]],
        }
        return FakeRowSet(quotes.get(code, []))

    @staticmethod
    def query_profit_data(code, year, quarter):
        # [code, pubDate, statDate, roeAvg, npMargin, gpMargin, netProfit,
        #  epsTTM, MBRevenue, totalShare, liqaShare]
        profits = {
            "sh.600519": [
                ["sh.600519", "2026-04-17", "2025-12-31", "0.34", "0.50", "0.92",
                 "85000000000", "60", "170000000000", "1256197800", "1256197800"],
            ],
        }
        return FakeRowSet(profits.get(code, []))

    @staticmethod
    def query_growth_data(code, year, quarter):
        # [code, pubDate, statDate, YOYEquity, YOYAsset, YOYNI, YOYEPSBasic, YOYPNI]
        growth = {
            "sh.600519": [
                ["sh.600519", "2026-04-17", "2025-12-31", "0.049470", "0.016358", "-0.045049", "-0.043415", "-0.045323"],
            ],
        }
        return FakeRowSet(growth.get(code, []))

    @staticmethod
    def query_balance_data(code, year, quarter):
        # [code, pubDate, statDate, currentRatio, quickRatio, cashRatio, YOYLiability, liabilityToAsset, assetToEquity]
        balance = {
            "sh.600519": [
                ["sh.600519", "2026-04-17", "2025-12-31", "5.09", "3.85", "1.04", "-0.12", "0.164154", "1.196392"],
            ],
        }
        return FakeRowSet(balance.get(code, []))

    @staticmethod
    def query_cash_flow_data(code, year, quarter):
        # [code, pubDate, statDate, CAToAsset, NCAToAsset, tangibleAssetToAsset, ebitToInterest, CFOToOR, CFOToNP, CFOToGr]
        cf = {
            "sh.600519": [
                ["sh.600519", "2026-04-17", "2025-12-31", "0.83", "0.17", "0.75", "", "0.36", "0.721158", "0.36"],
            ],
        }
        return FakeRowSet(cf.get(code, []))


class FakeBaostockConnector(BaostockConnector):
    def __init__(self, **kwargs):
        kwargs.setdefault("quarters", 2)
        kwargs.setdefault("enrich_sina", False)  # test baostock's native mapping only
        super().__init__(**kwargs)

    def _bs_login(self):
        FakeBaostock.login()  # mirror the real connector's login call
        return FakeBaostock


def test_code_conversion():
    assert _to_bs_code("600519") == "sh.600519"
    assert _to_bs_code("000001") == "sz.000001"
    assert _to_bs_code("300750") == "sz.300750"
    assert _to_bs_code("688981") == "sh.688981"


def test_quarter_ago():
    assert _quarter_ago(2025, 4, 0) == (2025, 4)
    assert _quarter_ago(2025, 1, 1) == (2024, 4)
    assert _quarter_ago(2026, 2, 6) == (2024, 4)


def test_financial_snapshot_maps_fields():
    connector = FakeBaostockConnector(tickers=["600519"], trade_date="2026-08-07")
    snapshots = connector.fetch_company_snapshots()
    financial = [s for s in snapshots if s.data_kind == "financial"]
    assert len(financial) >= 1
    s = financial[0]
    assert s.ticker == "600519"
    assert s.period.strftime("%Y-%m-%d") == "2025-12-31"
    assert s.revenue == 170000000000.0
    assert s.net_profit == 85000000000.0
    assert s.profit_growth == -0.045049  # YOYNI index 5
    assert s.gross_margin == 0.92
    assert s.net_margin == 0.50
    assert s.roe == 0.34
    assert s.debt_ratio == 0.164154
    assert s.shares == 1256197800.0
    # OCF derived: net_profit * CFOToNP
    assert s.operating_cash_flow == 85000000000.0 * 0.721158
    # Documented baostock gaps -> None
    assert s.revenue_growth is None
    assert s.order_growth is None
    assert s.net_assets is None
    assert s.is_demo is False


def test_market_snapshot_maps_fields():
    connector = FakeBaostockConnector(tickers=["600519"], trade_date="2026-08-07")
    snapshots = connector.fetch_company_snapshots()
    market = [s for s in snapshots if s.data_kind == "market"]
    assert len(market) == 1
    m = market[0]
    assert m.price == 1309.22
    assert m.pe == 19.786372
    assert m.pb == 6.041594
    assert m.shares == 1256197800.0
    assert m.market_cap == 1309.22 * 1256197800.0


def test_connector_skips_missing_quotes_but_keeps_financials():
    # 300750 has a quote but no financial rows; 000001 has nothing.
    connector = FakeBaostockConnector(tickers=["600519", "300750", "000001"], trade_date="2026-08-07")
    snapshots = connector.fetch_company_snapshots()
    tickers = {s.ticker for s in snapshots}
    assert "600519" in tickers
    assert "300750" in tickers  # market snapshot present even without financials
    assert "000001" not in tickers  # nothing at all in the fake source


def test_connector_logs_out_after_scan():
    FakeBaostock.login_calls = 0
    FakeBaostock.logout_calls = 0
    connector = FakeBaostockConnector(tickers=["600519"], trade_date="2026-08-07")
    connector.fetch_company_snapshots()
    assert FakeBaostock.login_calls == 1
    assert FakeBaostock.logout_calls == 1
