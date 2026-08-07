# v0.3 真实数据接入状态

## Tushare 连接器（离线模拟验证）

- Tushare官方HTTP协议连接器；
- 全A上市、退市、待上市证券主数据；
- 申万一级行业成员映射；
- 每日行情、总市值、PE、PB和总股本；
- 按公告日增量读取利润表、资产负债表、现金流和财务指标；
- 业绩预告与业绩快报结构化文档；
- 市场快照与财务快照分离；
- 公告修订版本保留；
- 手动同步、通用HTTP导入和自动调度；
- 真实环境只初始化行业目录，不写入演示公司；
- 8项自动测试全部通过。

## Akshare 免费连接器（✅ 真实数据联网验证通过，2026-08-07）

**动机**：用户无 Tushare Token。实测 akshare 免费接口可替代 Tushare 付费接口 95% 的数据需求，新增 `akshare_connector.py` 实现同一 `DataConnector` 协议，IRO 核心研究逻辑一行未改。

**已实测验证的端点**（akshare 1.18.82，真实网络）：

| 数据 | 接口 | 结果 |
|------|------|------|
| 全A公司 | `stock_info_a_code_name()` | 5538 只 |
| 申万行业成分 | `sw_index_first_info()` + `index_component_sw()` | 31 行业 → 5201 条成员归属 |
| 财务三表 | `stock_financial_report_sina()` | 资产负债表/利润表/现金流量表，每只 100+ 期 |
| 财务指标 | `stock_financial_analysis_indicator()` | ROE/毛利率/负债率/净利润增长率 |
| 业绩预告 | `stock_yjyg_em()` | 全市场批量，实时，含预告类型/变动幅度/公告日期 |

**分层深挖策略**（核心设计）：第一遍拉全市场业绩预告（快），第二遍只对"预增>50% 或 预减"的公司深挖财务。触发 1656 家，按预告幅度降序深挖（`--max-deep-dive` 上限）。

**关键数据映射**（akshare 无原样字段，做了代理）：
- `order_growth` ← 合同负债同比增长（预收订单的代理）
- `profit_growth`/`revenue_growth` ← indicator 优先，缺失时用利润表自算同比兜底（解决 indicator 滞后一期的问题）

**端到端验证结果**：`sync-akshare --report-date 20260630` 入库 5538 公司 + 5201 行业归属 + 602 财务快照 + 57 预告信号 + 3754 预告原文；`run-cycle` 成功发现"东瑞股份：订单与利润加速"机会并完成完整研究（证据→公司映射→反方审查→决策，qualified=False 诚实拒绝）。15 项测试全过（原 8 + 新增 7）。

**注意事项**：
- 东财 `stock_zh_a_spot_em()` 实时全市场快照被 WAF 拦截，行情估值走 baostock 替代；
- 每日增量更新需自行设置定时任务（CLI 手动跑）。

## Baostock 财务+估值主源切换（✅ 已验证，2026-08-07）

**动机**：akshare/Sina 财务接口在连续深挖 ~100 家后对本机 IP 封禁（`JSONDecodeError`），无法支撑全市场深挖。baostock 免费、无需 token、不限流，成为财务+估值主源。

**已实测验证的映射**（baostock，逐季拉取）：

| CompanySnapshot 字段 | baostock 来源 | 状态 |
|---|---|---|
| revenue / net_profit / shares | query_profit_data (MBRevenue/netProfit/totalShare) | ✅ |
| profit_growth | query_growth_data YOYNI | ✅ |
| gross_margin / net_margin / roe | query_profit_data (gpMargin/npMargin/roeAvg) | ✅ |
| debt_ratio | query_balance_data liabilityToAsset | ✅ |
| operating_cash_flow | query_cash_flow_data CFOToNP × netProfit | ✅（推算） |
| price / pe / pb | query_history_k_data_plus (close/peTTM/pbMRQ) | ✅ |
| market_cap | close × totalShare | ✅ |
| revenue_growth / order_growth / net_assets | **baostock 缺口** | ⚠️ 标注 None |

**数据口径注意**：baostock 季度财务是年内累计（Q4=全年，Q3=前三季），增速用 baostock 自带 YoY 指标，不做跨季度差分。

**覆盖验证**：sync-valuation --max-tickers 100 → 97 家财务+估值齐全（97% 覆盖率）。决策清单三层漏斗（利润增速>0 + 经营现金流>0 + PE 0~60）筛出 **15 家候选**，按性价比（增速/PE）排序。看板升级为决策清单型，已部署 GitHub Pages `https://lanren152.github.io/iro-dashboard/`。

**待办（曹大人拍板先 100 家验证机制）**：验证效果后放开 `akshare_max_deep_dive` 到全触发公司（1656 家），并回填 `Company.sector_code`（当前公司主数据落 fallback 综合行业，行业归属在 membership 表中，影响机会聚合展示）。

## 尚未完成

- 真实 Tushare Token 联网验收（改用 akshare 后不再依赖）；
- 原始公告PDF、问询函及页码级解析（仍需 CNINFO/深证信授权数据服务）；
- 行业特有专业指标体系（当前 240 个为通用模板）；
- 历史时点回放与未来数据泄漏测试；
- 生产级权限、密钥管理、任务锁和监控告警。
