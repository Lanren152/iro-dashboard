"""Tests for the free akshare connector.

The connector talks to akshare's network endpoints; the tests replace those
with deterministic fake DataFrames so the mapping logic is verified offline
(no token, no network). Endpoint column names mirror akshare 1.18.x exactly.
"""
import os
import pandas as pd

os.environ["DATABASE_URL"] = "sqlite:///./test_akshare_connector.db"
os.environ["AUTO_SEED"] = "false"

from app.connectors.akshare import AkshareConnector


class FakeAkShare:
    """Stands in for the akshare module with the subset of endpoints used."""

    def stock_info_a_code_name(self):
        return pd.DataFrame([
            {"code": "600519", "name": "贵州茅台"},
            {"code": "300750", "name": "宁德时代"},
            {"code": "000001", "name": "平安银行"},
        ])

    def stock_yjyg_em(self, date: str):
        # Company x profit-line indicator forecast rows.
        return pd.DataFrame([
            {
                "股票代码": "300750", "股票简称": "宁德时代", "预测指标": "归属于上市公司股东的净利润",
                "业绩变动": "预计2026年1-6月净利润同比大幅上升", "预测数值": 6.0e9,
                "业绩变动幅度": 120.5, "预告类型": "预增", "公告日期": "2026-08-05",
            },
            {
                "股票代码": "600519", "股票简称": "贵州茅台", "预测指标": "归属于上市公司股东的净利润",
                "业绩变动": "预计2026年1-6月净利润同比小幅上升", "预测数值": 5.0e10,
                "业绩变动幅度": 15.0, "预告类型": "略增", "公告日期": "2026-08-04",
            },
            {
                "股票代码": "000001", "股票简称": "平安银行", "预测指标": "归属于上市公司股东的净利润",
                "业绩变动": "预计2026年1-6月净利润同比大幅下降", "预测数值": -2.0e9,
                "业绩变动幅度": -55.0, "预告类型": "预减", "公告日期": "2026-08-03",
            },
        ])

    def sw_index_first_info(self):
        return pd.DataFrame([
            {"行业代码": "801780", "行业名称": "银行"},
            {"行业代码": "801760", "行业名称": "电力设备"},
        ])

    def index_component_sw(self, symbol: str):
        mapping = {
            "801760": pd.DataFrame([{"证券代码": "300750"}]),
            "801780": pd.DataFrame([{"证券代码": "000001"}]),
        }
        return mapping.get(symbol, pd.DataFrame())

    def stock_financial_report_sina(self, stock: str, symbol: str):
        # Two financial periods for the deep-dived company (300750).
        if stock == "sz300750" and symbol == "利润表":
            return pd.DataFrame([
                {"报告日": "20251231", "营业收入": 1.0e11, "归属于母公司的净利润": 1.5e10},
                {"报告日": "20250630", "营业收入": 8.0e10, "归属于母公司的净利润": 1.2e10},
            ])
        if stock == "sz300750" and symbol == "资产负债表":
            return pd.DataFrame([
                {"报告日": "20251231", "负债合计": 3.0e11, "股东权益": 2.5e11, "股本": 4.4e9, "合同负债": 4.0e10},
                {"报告日": "20250630", "负债合计": 2.8e11, "股东权益": 2.2e11, "股本": 4.4e9, "合同负债": 3.0e10},
            ])
        if stock == "sz300750" and symbol == "现金流量表":
            return pd.DataFrame([
                {"报告日": "20251231", "经营活动产生的现金流量净额": 2.0e10},
                {"报告日": "20250630", "经营活动产生的现金流量净额": 1.5e10},
            ])
        return pd.DataFrame()

    def stock_financial_analysis_indicator(self, symbol: str, start_year: str):
        if symbol == "300750":
            return pd.DataFrame([
                {
                    "日期": pd.Timestamp("2025-12-31"), "主营业务收入增长率(%)": 25.0,
                    "净利润增长率(%)": 30.0, "销售毛利率(%)": 28.0, "销售净利率(%)": 15.0,
                    "净资产收益率(%)": 12.0, "资产负债率(%)": 54.0,
                },
                {
                    "日期": pd.Timestamp("2025-06-30"), "主营业务收入增长率(%)": 20.0,
                    "净利润增长率(%)": 25.0, "销售毛利率(%)": 27.0, "销售净利率(%)": 14.0,
                    "净资产收益率(%)": 11.0, "资产负债率(%)": 55.0,
                },
            ])
        return pd.DataFrame()


class FakeAkshareConnector(AkshareConnector):
    def __init__(self, **kwargs):
        kwargs.setdefault("report_date", "20260630")
        super().__init__(**kwargs)

    def _ak(self):
        return FakeAkShare()


def test_fetch_companies_maps_full_list():
    connector = FakeAkshareConnector()
    companies = connector.fetch_companies()
    assert len(companies) == 3
    by_ticker = {c.ticker: c for c in companies}
    assert by_ticker["600519"].exchange == "sh"
    assert by_ticker["300750"].exchange == "sz"
    assert by_ticker["000001"].exchange == "sz"
    assert all(c.is_demo is False for c in companies)


def test_fetch_metrics_uses_profit_line_forecasts():
    connector = FakeAkshareConnector()
    metrics = connector.fetch_metrics()
    assert len(metrics) == 3
    values = {m.value: m for m in metrics}
    assert 120.5 in values
    assert values[120.5].metric_code == "forecast_earnings_growth"
    assert values[120.5].source_name == "akshare stock_yjyg_em"


def test_triggered_set_flags_material_profit_changes():
    connector = FakeAkshareConnector()
    triggered = connector._triggered_ticker_set()
    # 300750 pre-increase 120.5% (>50%) -> triggered
    assert "300750" in triggered
    # 000001 pre-decrease -55% (<-10%) -> triggered
    assert "000001" in triggered
    # 600519 only +15% -> not triggered
    assert "600519" not in triggered


def test_layered_deep_dive_only_for_triggered_companies():
    connector = FakeAkshareConnector()
    snapshots = connector.fetch_company_snapshots()
    tickers = {s.ticker for s in snapshots}
    assert "300750" in tickers  # triggered and has financial statements -> deep-dived
    assert "600519" not in tickers  # not triggered -> never deep-dived
    # 000001 is triggered but the fake source has no statements for it, so it
    # produces no snapshots (a real company with no data simply yields nothing).
    # Financial snapshot fields populated from the fake statements.
    s750 = [s for s in snapshots if s.ticker == "300750" and s.period.strftime("%Y%m%d") == "20251231"]
    assert len(s750) == 1
    row = s750[0]
    assert row.revenue == 1.0e11
    assert row.net_profit == 1.5e10
    assert row.profit_growth is not None and abs(row.profit_growth - 0.30) < 1e-9
    assert row.is_demo is False


def test_fetch_memberships_maps_shenwan_industry():
    connector = FakeAkshareConnector()
    memberships = connector.fetch_company_memberships()
    assert len(memberships) == 2
    by_ticker = {m.ticker: m for m in memberships}
    assert by_ticker["300750"].sector_code == "09"  # 电力设备
    assert by_ticker["000001"].sector_code == "23"  # 银行
    assert all(m.is_demo is False for m in memberships)


def test_deep_dive_orders_by_forecast_magnitude():
    connector = FakeAkshareConnector()
    order = connector._deep_dive_order()
    # 300750 (+120.5%) ranks above 000001 (-55%) by |change|.
    assert order[0] == "300750"
    assert "000001" in order


def test_fetch_documents_are_traceable():
    connector = FakeAkshareConnector()
    docs = connector.fetch_documents()
    assert len(docs) == 3
    assert all(d.content_hash for d in docs)
    assert all(d.published_at is not None for d in docs)
    tickers = {d.company_ticker for d in docs}
    assert "300750" in tickers
