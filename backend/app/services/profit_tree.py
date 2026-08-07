from sqlalchemy import select

from ..db import AppSession as Session
from ..models import ProfitDriver


GENERIC_TREE = [
    ("net_profit", None, "净利润", "output", "", "revenue - variable_cost - fixed_cost - tax", 1, 0),
    ("revenue", "net_profit", "营业收入", "revenue", "currency", "volume * price", 1, 10),
    ("volume", "revenue", "销量/业务量", "volume", "unit", "demand * market_share * capacity", 1, 11),
    ("demand", "volume", "行业需求", "demand", "index", "", 1, 12),
    ("market_share", "volume", "市场份额", "share", "%", "", 1, 13),
    ("capacity", "volume", "有效产能与利用率", "capacity", "%", "", 1, 14),
    ("price", "revenue", "产品价格/客单价", "price", "currency/unit", "", 1, 15),
    ("variable_cost", "net_profit", "变动成本", "cost", "currency", "volume * unit_cost", -1, 20),
    ("unit_cost", "variable_cost", "单位成本", "cost", "currency/unit", "raw_material + energy + labor + depreciation", -1, 21),
    ("fixed_cost", "net_profit", "期间费用与固定成本", "expense", "currency", "", -1, 30),
    ("tax", "net_profit", "税费", "tax", "currency", "pre_tax_profit * tax_rate", -1, 40),
    ("shares", "net_profit", "股本变化", "shares", "shares", "EPS = net_profit / shares", -1, 50),
]


class ProfitTreeService:
    def __init__(self, session: Session):
        self.session = session

    def ensure(self, company_id: int) -> list[ProfitDriver]:
        existing = self.session.exec(select(ProfitDriver).where(ProfitDriver.company_id == company_id)).all()
        if existing:
            return existing
        ids = {}
        for code, parent_code, name, driver_type, unit, formula, sign, order in GENERIC_TREE:
            node = ProfitDriver(
                company_id=company_id,
                parent_id=ids.get(parent_code),
                code=code,
                name=name,
                driver_type=driver_type,
                unit=unit,
                formula=formula,
                sign=sign,
                sort_order=order,
                source="system_generic",
            )
            self.session.add(node)
            self.session.flush()
            ids[code] = node.id
        self.session.commit()
        return self.session.exec(select(ProfitDriver).where(
            ProfitDriver.company_id == company_id
        ).order_by(ProfitDriver.sort_order)).all()

    def as_tree(self, company_id: int) -> list[dict]:
        nodes = self.ensure(company_id)
        by_parent: dict[int | None, list[ProfitDriver]] = {}
        for node in nodes:
            by_parent.setdefault(node.parent_id, []).append(node)

        def render(parent_id):
            return [{
                "id": n.id,
                "code": n.code,
                "name": n.name,
                "driver_type": n.driver_type,
                "unit": n.unit,
                "formula": n.formula,
                "sign": n.sign,
                "children": render(n.id),
            } for n in sorted(by_parent.get(parent_id, []), key=lambda x: x.sort_order)]

        return render(None)
