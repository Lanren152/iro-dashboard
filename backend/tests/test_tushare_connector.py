from app.connectors.tushare import TushareConnector


class FakeTushareConnector(TushareConnector):
    def __init__(self):
        super().__init__(token="test")

    def _call_paged(self, api_name, params=None, fields="", page_size=2000, max_pages=100):
        data = {
            "index_member_all": [
                {"l1_code": "801730", "l1_name": "电力设备", "l2_code": "x", "l2_name": "电池", "l3_code": "y", "l3_name": "锂电池", "ts_code": "300750.SZ", "is_new": "Y"},
            ],
            "stock_basic": [
                {"ts_code": "300750.SZ", "symbol": "300750", "name": "宁德时代", "area": "福建", "industry": "电气设备", "market": "创业板", "exchange": "SZSE", "list_status": "L", "list_date": "20180611", "delist_date": None, "is_hs": "H"}
            ] if (params or {}).get("list_status") == "L" else [],
            "daily_basic": [
                {"ts_code": "300750.SZ", "trade_date": "20260803", "close": 300, "pe": 25, "pb": 5, "total_share": 440000, "total_mv": 132000000}
            ],
            "income_vip": [
                {"ts_code": "300750.SZ", "ann_date": "20260804", "f_ann_date": "20260804", "end_date": "20260630", "revenue": 200000000000, "n_income_attr_p": 30000000000}
            ],
            "balancesheet_vip": [
                {"ts_code": "300750.SZ", "ann_date": "20260804", "f_ann_date": "20260804", "end_date": "20260630", "total_liab": 300000000000, "total_hldr_eqy_exc_min_int": 250000000000, "total_share": 4400000000}
            ],
            "cashflow_vip": [
                {"ts_code": "300750.SZ", "ann_date": "20260804", "f_ann_date": "20260804", "end_date": "20260630", "n_cashflow_act": 40000000000}
            ],
            "fina_indicator_vip": [
                {"ts_code": "300750.SZ", "ann_date": "20260804", "end_date": "20260630", "revenue_yoy": 30, "netprofit_yoy": 40, "grossprofit_margin": 25, "netprofit_margin": 15, "roe": 12, "debt_to_assets": 54}
            ],
            "forecast_vip": [
                {"ts_code": "300750.SZ", "ann_date": "20260804", "end_date": "20261231", "type": "预增", "p_change_min": 20, "p_change_max": 30}
            ],
            "express_vip": [],
        }
        return data.get(api_name, [])


def test_tushare_mapping_separates_market_and_financial_revisions():
    connector = FakeTushareConnector()
    connector.trade_date = "20260803"
    connector.announcement_date = "20260804"

    companies = connector.fetch_companies()
    assert companies[0].ticker == "300750.SZ"
    assert companies[0].sector_code == "09"
    memberships = connector.fetch_company_memberships()
    assert memberships[0].sector_code == "09"

    snapshots = connector.fetch_company_snapshots()
    market = next(x for x in snapshots if x.data_kind == "market")
    financial = next(x for x in snapshots if x.data_kind == "financial")
    assert market.version_key == "20260803"
    assert market.market_cap == 1320000000000
    assert financial.version_key == "20260804"
    assert financial.revenue_growth == .30
    assert financial.debt_ratio == .54

    documents = connector.fetch_documents()
    assert documents[0].company_ticker == "300750.SZ"
    assert documents[0].source_type == "licensed_financial_data"
