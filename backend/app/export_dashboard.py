"""Export the IRO research state to a self-contained static HTML dashboard.

Reads the SQLite database directly (no backend needed at view time) and
renders a responsive, offline-capable dashboard that can be deployed to any
static host (vnext / GitHub Pages). Data is embedded in the HTML; the only
external dependency is Chart.js from a CDN (degrades gracefully offline).

Usage:
    PYTHONPATH=backend python -m app.export_dashboard -o dashboard/index.html
"""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select, text

from .db import SessionLocal, init_db
from .models import Company, CompanySnapshot, Opportunity, SourceDocument

# ──────────────────────────────────────────────────────────────
# 设计令牌 — 与原前端 styles.css 一致（Bento + 纸张质感 + 语义配色）
# ──────────────────────────────────────────────────────────────
CSS = """
:root{
  --bg:#0b0f14; --panel:#121a22; --panel2:#0e141b; --line:#1f2a35;
  --ink:#e8eef4; --muted:#8fa0b0; --dim:#5c6b7a;
  --up:#ff5a5f; --up-bg:rgba(255,90,95,.12);  /* A股红涨 */
  --down:#2dd4a7; --down-bg:rgba(45,212,167,.12); /* A股绿跌 */
  --accent:#4da3ff; --accent-bg:rgba(77,163,255,.12);  /* 信任蓝 */
  --warn:#f5a623; --warn-bg:rgba(245,166,35,.12);
  --good:#2dd4a7; --watch:#4da3ff;
}
*{box-sizing:border-box}
.skip-link{position:absolute;left:-9999px;top:0;background:var(--accent);color:#fff;padding:10px 16px;border-radius:0 0 10px 0;z-index:99;font-size:14px}
.skip-link:focus{left:0}
html,body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,"Noto Sans SC","PingFang SC",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
main{width:min(760px,calc(100% - 28px));margin:0 auto;padding:28px 0 56px}
header{border-bottom:1px solid var(--line);padding-bottom:22px;margin-bottom:18px}
.eyebrow{font-size:11px;letter-spacing:.22em;color:var(--accent);font-weight:700;text-transform:uppercase}
h1{font-size:clamp(26px,5vw,40px);letter-spacing:-.045em;line-height:1.08;margin:10px 0 10px;font-weight:700}
header p{color:var(--muted);line-height:1.7;margin:0;font-size:14px}
.meta-line{font:11px ui-monospace;color:var(--dim);margin-top:10px}

/* 顶部数字条 */
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0 22px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.stat strong{font-size:24px;display:block;letter-spacing:-.03em}
.stat span{color:var(--muted);font-size:12px}

/* 决策清单标题 */
.section-title{margin:26px 0 14px}
.section-title h2{font-size:18px;margin:0;letter-spacing:-.02em}
.section-title p{color:var(--muted);font-size:12px;margin:5px 0 0;line-height:1.6}

/* 候选卡片流 */
.cards{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;overflow:hidden}
.card summary{display:block;cursor:pointer;padding:18px 18px 14px;list-style:none;outline:none}
.card summary::-webkit-details-marker{display:none}
.card summary:focus-visible{box-shadow:inset 0 0 0 2px var(--accent)}
.card[open]{border-color:var(--accent)}
.card-top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.card-name{min-width:0}
.card-name h3{margin:0;font-size:17px;letter-spacing:-.02em}
.card-name .code{font:11px ui-monospace;color:var(--dim);margin-top:3px}
.card-highlight{text-align:right;flex-shrink:0}
.card-highlight .growth{font-size:22px;font-weight:700;color:var(--up);letter-spacing:-.03em}
.card-highlight .tagline{font-size:11px;color:var(--muted);margin-top:2px}
.card-story{margin:12px 0 0;color:var(--ink);font-size:14px;line-height:1.65;background:var(--panel2);border-radius:10px;padding:11px 13px}
.card-story .why{color:var(--muted);font-size:12px;margin-top:6px;line-height:1.55}
.card-metrics{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.metric{background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:7px 11px;font-size:12px}
.metric b{display:block;font-size:14px;margin-top:2px}
.metric span{color:var(--muted);font-size:10px;letter-spacing:.04em}
.metric .up{color:var(--up)}.metric .down{color:var(--down)}.metric .flat{color:var(--muted)}
.card-verdict{margin-top:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.pill{font-size:12px;font-weight:600;padding:5px 12px;border-radius:99px}
.pill.good{background:var(--good);color:#06261d}
.pill.watch{background:var(--accent);color:#04213f}
.pill.warn{background:var(--warn);color:#2a1a04}
.card-risk{font-size:12px;color:var(--warn);margin:8px 14px 0;line-height:1.5}

/* 卡片展开详情（原生 details[open]） */
.detail{margin:0 18px 16px;border-top:1px solid var(--line);padding-top:14px}
.detail h4{font-size:12px;color:var(--muted);margin:0 0 8px;text-transform:uppercase;letter-spacing:.08em}
.detail table{width:100%;border-collapse:collapse;font-size:12px}
.detail th{text-align:left;font-weight:500;color:var(--muted);font-size:12px;text-transform:none;letter-spacing:0;padding:7px 6px;border-bottom:1px solid var(--line)}
.detail td{padding:7px 6px;border-bottom:1px solid var(--line)}
.detail tr:last-child td{border-bottom:0}
.detail td.num{font:12px ui-monospace;text-align:right}

/* 副区块（预告分布 / 机会） */
.sub-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:26px}
.sub-panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
.sub-panel h3{font-size:14px;margin:0 0 10px;letter-spacing:-.01em}
.opp-list{list-style:none;margin:0;padding:0}
.opp-item{padding:10px 0;border-bottom:1px solid var(--line)}
.opp-item:last-child{border-bottom:0}
.opp-item h4{margin:0;font-size:13px}
.opp-item p{margin:5px 0 0;color:var(--muted);font-size:12px;line-height:1.55}
.opp-score{font-size:18px;font-weight:700;color:var(--accent)}
.chart-wrap{position:relative;height:200px}
.sector-cloud{display:flex;flex-wrap:wrap;gap:6px}
.sector-cloud span{padding:5px 9px;border:1px solid var(--line);border-radius:7px;font-size:11px;background:var(--panel2);color:var(--muted)}
.empty{padding:26px 10px;color:var(--muted);font-size:13px;text-align:center}
footer{border-top:1px solid var(--line);margin-top:30px;padding-top:18px;color:var(--dim);font-size:11px;line-height:1.7}
.hint{text-align:center;color:var(--dim);font-size:11px;margin-top:10px}
@media(max-width:560px){.stats{grid-template-columns:repeat(3,1fr)}.sub-grid{grid-template-columns:1fr}.card-highlight .growth{font-size:19px}}
"""


def _fmt_float(v: float | None, digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}"


def _pct(v: float | None) -> str:
    if v is None:
        return "—"
    pct = v * 100
    sign = "+" if pct >= 0 else ""
    cls = "pos" if pct >= 0 else "neg"
    return f'<span class="{cls}">{sign}{pct:.1f}%</span>'


def _fmt_money(v: float | None) -> str:
    if v is None:
        return "—"
    abs_v = abs(v)
    if abs_v >= 1e8:
        out = f"{v / 1e8:.1f}亿"
    elif abs_v >= 1e4:
        out = f"{v / 1e4:.0f}万"
    else:
        out = f"{v:.0f}"
    return out


def collect(session) -> dict:
    counts = {
        "sectors": session.execute(text("SELECT COUNT(*) FROM sector")).scalar() or 0,
        "companies": session.execute(text("SELECT COUNT(*) FROM company")).scalar() or 0,
        "snapshots": session.execute(text("SELECT COUNT(*) FROM company_snapshot")).scalar() or 0,
        "metrics": session.execute(text("SELECT COUNT(*) FROM metric_observation")).scalar() or 0,
        "documents": session.execute(text("SELECT COUNT(*) FROM source_document")).scalar() or 0,
        "opportunities": session.execute(text("SELECT COUNT(*) FROM opportunity")).scalar() or 0,
    }
    opportunities = session.execute(select(Opportunity)).scalars().all()
    opp_list = []
    for op in opportunities:
        origin_company = None
        if op.origin_company_id:
            origin_company = session.get(Company, op.origin_company_id)
        opp_list.append({
            "id": op.id,
            "title": op.title,
            "sector": op.sector_code,
            "origin": op.origin,
            "stage": op.stage,
            "score": op.score,
            "confidence": op.confidence,
            "thesis": op.thesis,
            "profit_transmission": op.profit_transmission,
            "market_pricing": op.market_pricing,
            "missing_evidence": op.missing_evidence,
            "falsification": op.falsification_conditions,
            "origin_ticker": origin_company.ticker if origin_company else None,
            "origin_name": origin_company.name if origin_company else None,
        })

    # 深挖公司：最近一期财务 + 最近一期估值（market snapshot）join
    # 每家公司取最新的 financial 快照和最新的 market 快照，合成一张决策清单。
    fin_rows = session.execute(text("""
        SELECT c.ticker, c.name, cs.period, cs.net_profit, cs.profit_growth,
               cs.revenue_growth, cs.operating_cash_flow, cs.order_growth
        FROM company_snapshot cs JOIN company c ON c.id = cs.company_id
        WHERE cs.data_kind = 'financial'
        ORDER BY cs.period DESC, cs.net_profit DESC
    """)).all()
    mk_rows = session.execute(text("""
        SELECT c.ticker, cs.price, cs.pe, cs.pb, cs.market_cap
        FROM company_snapshot cs JOIN company c ON c.id = cs.company_id
        WHERE cs.data_kind = 'market'
        ORDER BY cs.period DESC
    """)).all()

    fin_latest: dict[str, dict] = {}
    for r in fin_rows:
        if r.ticker in fin_latest:
            continue
        fin_latest[r.ticker] = {
            "ticker": r.ticker, "name": r.name, "period": r.period,
            "net_profit": r.net_profit, "profit_growth": r.profit_growth,
            "revenue_growth": r.revenue_growth, "ocf": r.operating_cash_flow,
            "order_growth": r.order_growth,
        }
    mk_latest: dict[str, dict] = {}
    for r in mk_rows:
        if r.ticker in mk_latest:
            continue
        mk_latest[r.ticker] = {
            "price": r.price, "pe": r.pe, "pb": r.pb, "market_cap": r.market_cap,
        }

    deep_dive: list[dict] = []
    for ticker, fin in fin_latest.items():
        item = dict(fin)
        item.update(mk_latest.get(ticker, {}))
        deep_dive.append(item)
        if len(deep_dive) >= 200:
            break

    # 决策清单（三层漏斗）：
    # ① 利润在变：profit_growth 为正（业绩预告已触发）
    # ② 现金流真实：经营现金流 > 0
    # ③ 市场未充分定价：有 PE 且 PE 在健康区间（>0 且 < 60）
    # 每只候选配人话解读：业绩变动原因（预告原文）+ 三层判定 + 术语翻译。
    # 先取每家的业绩预告原因。
    forecast_reason: dict[str, str] = {}
    rows = session.execute(text("""
        SELECT c.ticker, sd.parsed_text FROM source_document sd
        JOIN company c ON c.id = sd.company_id
        WHERE sd.source_name = 'akshare stock_yjyg_em'
    """)).all()
    for r in rows:
        try:
            d = json.loads(r[1])
        except Exception:
            continue
        reason = str(d.get("业绩变动原因") or "").strip()
        ftype = str(d.get("预告类型") or "")
        if reason and r[0] not in forecast_reason:
            forecast_reason[r[0]] = (reason[:120] + "…") if len(reason) > 120 else reason
        # 记录预告类型（判断用）
        if r[0] not in forecast_reason:
            forecast_reason[r[0]] = ""

    candidates = []
    for item in deep_dive:
        pg = item.get("profit_growth")
        ocf = item.get("ocf")
        pe = item.get("pe")
        if pg is None or ocf is None or pe is None:
            continue
        if pg <= 0 or ocf <= 0 or pe <= 0 or pe > 60:
            continue
        # 性价比分：利润增速越高、PE 越低越好
        value_score = pg * 100 / max(pe, 1)
        item["value_score"] = round(value_score, 1)
        # 人话翻译：pg 是小数（1.0 = +100%）。暴增N倍 = pg 的整数倍。
        pg_mult = pg  # 1.0 = 翻倍
        payback = pe  # PE = 回本年限（年）
        item["human_growth"] = f"利润暴增{pg_mult:.0f}倍" if pg_mult >= 2 else (
            f"利润增长{pg_mult * 100:.0f}%" if pg_mult >= 0.5 else f"利润增长{pg_mult * 100:.0f}%")
        item["human_pe"] = f"约{payback:.0f}年回本" if payback else "—"
        item["human_cash"] = "经营现金流为正" if ocf > 0 else "经营现金流为负"
        item["cash_positive"] = ocf > 0
        # 判定
        if pe < 15 and pg_mult >= 1:
            verdict, verdict_cls = "值得深挖", "good"
        elif ocf <= 0 or pg_mult < 0.5:
            verdict, verdict_cls = "有隐患", "warn"
        else:
            verdict, verdict_cls = "观察", "watch"
        item["verdict"] = verdict
        item["verdict_cls"] = verdict_cls
        item["reason"] = forecast_reason.get(item["ticker"], "")
        candidates.append(item)
    candidates.sort(key=lambda x: -x["value_score"])
    candidates = candidates[:30]

    # 业绩预告信号分布（按预告类型）
    forecast_dist = {}
    rows = session.execute(text("""
        SELECT parsed_text FROM source_document
        WHERE source_name = 'akshare stock_yjyg_em'
    """)).scalars().all()
    for pt in rows:
        try:
            row = json.loads(pt)
            ftype = row.get("预告类型")
            if ftype:
                forecast_dist[ftype] = forecast_dist.get(ftype, 0) + 1
        except Exception:
            continue
    forecast_top = sorted(forecast_dist.items(), key=lambda x: -x[1])[:10]

    # 行业覆盖（有公司快照的行业）
    sector_rows = session.execute(text("""
        SELECT s.name, COUNT(DISTINCT c.id) FROM company c
        JOIN sector s ON s.code = c.sector_code
        GROUP BY s.name ORDER BY COUNT(DISTINCT c.id) DESC
    """)).all()
    sectors = [{"name": r[0], "count": r[1]} for r in sector_rows[:20]]

    return {
        "counts": counts,
        "opportunities": opp_list,
        "deep_dive": deep_dive,
        "candidates": candidates,
        "forecast_top": forecast_top,
        "sectors": sectors,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _render_opp(op: dict) -> str:
    return f"""
<li class="opp-item">
  <h4>{html.escape(op["title"] or "")}</h4>
  <p>{html.escape(op["thesis"] or "")}</p>
</li>"""


def _render_card(x: dict) -> str:
    """一只有人话解读的候选卡片（原生 details/summary 展开，a11y 友好）。"""
    growth = html.escape(x.get("human_growth", "利润增长"))
    growth_pct = _pct(x.get("profit_growth"))
    payback = html.escape(x.get("human_pe", "—"))
    cash_ok = bool(x.get("cash_positive"))
    cash_text = html.escape(x.get("human_cash", "—"))
    cash_arrow = "▲" if cash_ok else "▼"
    pe_val = x.get("pe")
    pb_val = x.get("pb")
    mc = x.get("market_cap")
    mc_text = _fmt_money(mc) if mc else "—"
    ocf_text = _fmt_money(x.get("ocf"))
    story = html.escape(x.get("reason") or "")
    why = html.escape(x.get("why") or "")
    verdict = x.get("verdict", "观察")
    vcls = x.get("verdict_cls", "watch")
    ticker = html.escape(x.get("ticker") or "")
    name = html.escape(x.get("name") or "")

    # 风险提示：现金流为负是最常见的隐患
    risk = ""
    if not cash_ok:
        risk = f"⚠️ 经营现金流为负（{ocf_text}）——利润暴增可能只是账面数字，增长质量需验证。"
    elif pe_val and pe_val > 40:
        risk = f"⚠️ PE {pe_val:.0f} 已偏高——利润暴增可能已被市场部分定价。"
    detail_rows = "".join(
        f"<tr><th scope='row'>{html.escape(k)}</th><td class='num'>{v}</td></tr>"
        for k, v in (
            ("净利润", _fmt_money(x.get("net_profit"))),
            ("利润增速", growth_pct),
            ("收入增速", _pct(x.get("revenue_growth"))),
            ("经营现金流", ocf_text),
            ("PE（回本年数）", f"{pe_val:.1f}" if pe_val else "—"),
            ("PB", f"{pb_val:.2f}" if pb_val else "—"),
            ("市值", mc_text),
        )
    )
    return f"""
<li class="card">
  <details>
    <summary aria-label="{name}，{growth}，判定{verdict}">
      <div class="card-top">
        <div class="card-name">
          <h3>{name}</h3>
          <div class="code">{ticker}</div>
        </div>
        <div class="card-highlight">
          <div class="growth" aria-hidden="true">{growth}</div>
          <div class="tagline">{growth_pct}</div>
        </div>
      </div>
      <div class="card-story">
        <div class="why">{why}</div>
        {('<div style="margin-top:8px">' + story + '</div>') if story else ''}
      </div>
      <div class="card-metrics">
        <div class="metric"><span>回本年限</span><b class="flat">{payback}</b></div>
        <div class="metric"><span>现金流</span><b class="{'up' if cash_ok else 'down'}">{cash_arrow} {cash_text}</b></div>
        <div class="metric"><span>市值</span><b class="flat">{mc_text}</b></div>
      </div>
      <div class="card-verdict">
        <span class="pill {vcls}">判定：{verdict}</span>
        <span style="color:var(--dim);font-size:11px" aria-hidden="true">点按展开财务明细</span>
      </div>
      {('<div class="card-risk">' + risk + '</div>') if risk else ''}
    </summary>
    <div class="detail">
      <h4>财务明细（最近一期）</h4>
      <table>
        <caption style="position:absolute;left:-9999px">{name} 财务明细</caption>
        <tbody>{detail_rows}</tbody>
      </table>
    </div>
  </details>
</li>"""


def build_html(data: dict) -> str:
    c = data["counts"]
    opp_html = "".join(_render_opp(o) for o in data["opportunities"]) or \
        '<div class="empty">当前无研究机会。运行 run-cycle 后此处会展示发现的候选方向。</div>'

    # 决策清单：候选卡片流（利润暴增 + 现金流真实 + 估值未充分定价）
    cand_cards = "".join(_render_card(x) for x in data["candidates"]) or \
        '<div class="empty">暂无满足三层漏斗的候选——需先运行 sync-akshare + sync-valuation 补充数据。</div>'
    cand_section = f"""
<section class="section-title" aria-labelledby="cand-heading">
  <h2 id="cand-heading">候选清单</h2>
  <p>利润在变 × 现金流真实 × 估值未充分定价 · 按性价比（利润增速/PE）排序 · 点按卡片看财务明细</p>
</section>
<ul class="cards">{cand_cards}</ul>"""

    deep_rows = "".join(
        f"<tr><td>{html.escape(d['ticker'])}</td><td>{html.escape(d['name'])}</td>"
        f"<td class='num'>{_fmt_money(d['net_profit'])}</td>"
        f"<td class='num'>{_pct(d['profit_growth'])}</td>"
        f"<td class='num'>{_pct(d['revenue_growth'])}</td>"
        f"<td class='num'>{_fmt_money(d['ocf'])}</td>"
        f"<td class='num'>{_fmt_float(d.get('pe'), 1)}</td>"
        f"<td class='num'>{_fmt_float(d.get('pb'), 2)}</td></tr>"
        for d in data["deep_dive"]
    ) or '<tr><td colspan="8" class="empty">尚无深挖财务数据</td></tr>'

    fore_rows = "".join(
        f"<tr><td>{html.escape(t)}</td><td class='num'><b>{n}</b></td></tr>"
        for t, n in data["forecast_top"]
    ) or '<tr><td colspan="2" class="empty">暂无预告数据</td></tr>'

    sector_html = "".join(
        f"<span>{html.escape(s['name'])} <b style='font:10px ui-monospace;color:#989b94'>{s['count']}</b></span>"
        for s in data["sectors"]
    )

    charts_js = ""
    if data["forecast_top"]:
        labels = json.dumps([t for t, _ in data["forecast_top"]], ensure_ascii=False)
        values = json.dumps([n for _, n in data["forecast_top"]])
        charts_js = f"""
<div class="chart-wrap"><canvas id="fc"></canvas></div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
document.addEventListener('DOMContentLoaded', () => {{
  const el = document.getElementById('fc');
  if (!el || typeof Chart === 'undefined') return;
  new Chart(el, {{ type: 'bar', data: {{
    labels: {labels},
    datasets: [{{ label: '预告公司数', data: {values},
      backgroundColor: '#4da3ff', borderRadius: 5, barPercentage: .7 }}]
  }}, options: {{ responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, title: {{ display: true, text: '业绩预告类型分布（全市场）', color: '#8fa0b0', font: {{ size: 12 }} }} }},
    scales: {{ y: {{ beginAtZero: true, ticks: {{ color: '#5c6b7a' }}, grid: {{ color: '#1f2a35' }} }},
              x: {{ ticks: {{ color: '#8fa0b0' }}, grid: {{ display: false }} }} }} }} }});
}});
</script>"""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="description" content="全市场候选雷达：利润在变、现金流真实、估值未充分定价的A股候选清单"/>
<title>投资候选雷达 · {data["generated_at"]}</title>
<style>{CSS}</style>
</head>
<body>
<a class="skip-link" href="#cand-heading">跳到候选清单</a>
<main>
  <header>
    <div>
      <div class="eyebrow">投资研究 · 候选雷达</div>
      <h1>今天该关注谁</h1>
      <p>从全市场找利润在变、现金流真实、市场还没充分定价的票。点卡片看财务明细。</p>
      <div class="meta-line">数据截止 {data["generated_at"]} · 数据源：业绩预告 + baostock 财务/估值</div>
    </div>
  </header>

  <section class="stats">
    <div class="stat"><strong>{c["opportunities"]}</strong><span>研究机会</span></div>
    <div class="stat"><strong>{len(data["candidates"])}</strong><span>候选中</span></div>
    <div class="stat"><strong>{c["companies"]}</strong><span>覆盖公司</span></div>
  </section>

  {cand_section}

  <section class="sub-grid">
    <div class="sub-panel">
      <h3>研究机会</h3>
      <ul class="opp-list">{opp_html}</ul>
    </div>
    <div class="sub-panel">
      <h3>业绩预告分布（全市场）</h3>
      {charts_js}
    </div>
  </section>

  <div class="hint">完整财务表（{len(data["deep_dive"])} 家深挖）点击下方展开</div>

  <footer>
    投资研究 OS · 数据源：akshare 业绩预告 + baostock 财务/估值 · 免责声明：此页为研究系统输出，不构成投资建议。前瞻判断存在不确定性，请独立验证后再做决策。
  </footer>
</main>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Export IRO research state to static HTML dashboard")
    parser.add_argument("-o", "--output", default="dashboard/index.html", help="output HTML path")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as session:
        data = collect(session)
    html_out = build_html(data)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out, encoding="utf-8")
    size = out_path.stat().st_size
    print(f"看板已导出：{out_path.resolve()} ({size / 1024:.1f} KB)")
    print(f"  机会 {data['counts']['opportunities']} | 深挖公司 {len(data['deep_dive'])} | 预告类型 {len(data['forecast_top'])} | 行业 {len(data['sectors'])}")


if __name__ == "__main__":
    main()
