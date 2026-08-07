# 真实A股数据接入操作

## 推荐的第一条真实数据链路

第一版使用 Tushare Pro 提供全A证券主数据、申万行业成员、每日行情估值、财务报表增量、业绩预告和业绩快报。原始公告PDF与交易所问询函随后接入深证信/CNINFO授权数据服务，不把不稳定网页抓取作为生产主链路。

## 1. 准备凭据

在 Tushare Pro 获取 Token，并确认账号具有以下接口权限：

- `stock_basic`
- `index_member_all`
- `trade_cal`
- `daily_basic`
- `income_vip`
- `balancesheet_vip`
- `cashflow_vip`
- `fina_indicator_vip`
- `forecast_vip`
- `express_vip`

如果暂时没有财务VIP接口权限，可以先同步公司、行业和每日行情，财务接口失败会在同步日志中明确报错，不能伪装为成功。

## 2. 配置环境

复制环境文件：

```bash
cp .env.example .env
```

至少修改：

```env
AUTO_SEED=false
DEMO_MODE=false
TUSHARE_TOKEN=你的Token
TUSHARE_API_URL=http://api.tushare.pro
REAL_DATA_SYNC_ENABLED=true
REAL_DATA_SYNC_MINUTES=60
MODEL_PROVIDER=heuristic
```

模型可以稍后再开。先验证数据完整性，不要让大模型掩盖数据错误。

## 3. 启动数据库和后端

```bash
docker compose up -d db backend
```

初始化40个一级行业及指标定义，但不写入演示公司：

```bash
docker compose run --rm backend python -m app.cli init-taxonomy
```

`seed` 命令只用于演示环境；真实环境使用 `init-taxonomy`。当 `AUTO_SEED=true` 且 `DEMO_MODE=false` 时，后端和调度器也只会初始化行业与指标定义。

## 4. 手动执行第一次真实同步

先明确指定日期，便于核验：

```bash
docker compose run --rm backend \
  python -m app.cli sync-tushare \
  --trade-date 20260803 \
  --announcement-date 20260804
```

命令会同步：

- 上市、退市和待上市证券主数据；
- 最新申万一级行业归属；
- 指定交易日的收盘价、市值、PE、PB和总股本；
- 指定公告日披露的利润表、资产负债表、现金流量表和财务指标；
- 指定公告日的业绩预告和业绩快报结构化记录。

正常输出示例：

```json
{
  "provider": "tushare",
  "trade_date": "20260803",
  "announcement_date": "20260804",
  "companies": 5000,
  "memberships": 5000,
  "company_snapshots": 5300,
  "documents": 120
}
```

具体数量以当日市场和账号权限为准。

第二次及以后可跳过公司主表，减少调用：

```bash
docker compose run --rm backend \
  python -m app.cli sync-tushare --skip-master
```

系统会自动查找当前月份最近一个开市日，并使用当前UTC日期同步财务公告增量。

## 5. 启用自动同步

确认手动同步正确后启动调度器：

```bash
docker compose up -d scheduler mcp
```

调度器根据：

```env
REAL_DATA_SYNC_ENABLED=true
REAL_DATA_SYNC_MINUTES=60
RESEARCH_CYCLE_MINUTES=60
```

自动执行数据同步和研究周期。公司主表与行业归属每天刷新一次；行情、财务和预告按同步周期增量读取。接口调用失败会写入日志，不会把空数据当成有效数据。

查看日志：

```bash
docker compose logs -f scheduler
```

## 6. 验证数据库不是演示数据

```bash
curl http://localhost:8000/api/dashboard
curl 'http://localhost:8000/api/companies?limit=20'
```

检查：

- 股票代码使用 `000001.SZ`、`600000.SH`、`920xxx.BJ` 等真实格式；
- `is_demo=false`；
- 公司数量覆盖全市场；
- 市场快照 `data_kind=market`；
- 财务快照 `data_kind=financial`；
- 财务快照的 `version_key` 为实际公告日，用于保留后续修订。

## 7. 接入CNINFO原始公告

Tushare链路解决标准化公司、行情和财务数据，但不能取代原始公告PDF。生产系统应向深证信数据服务申请公告API权限，然后增加 `CninfoConnector`，输出当前系统已经支持的 `SourceDocumentInput`：

```text
source_type = exchange_disclosure
source_name = CNINFO
published_at = 公告发布时间
data_period = 报告期
company_ticker = 证券代码
content_hash = 原始文件哈希
raw_path = PDF本地或对象存储地址
parsed_text = 带页码的解析文本
credibility = 1.0
```

原始PDF必须保存，AI摘要不能替代原文件。

## 8. Codex和Claude如何参与

数据同步由服务器调度器负责，不由聊天会话负责。Codex和Claude通过当前MCP服务读取同一数据库：

```text
http://localhost:8001/mcp
```

Codex主要处理连接器开发、字段变更、失败修复、测试和部署；Claude或另一个研究模型负责长文档阅读、产业研究和独立反方审查。API密钥保存在服务器环境变量或密钥管理系统中，不放进提示词、Git仓库或聊天消息。

## 当前边界

连接器已经按Tushare官方HTTP返回格式实现，并通过模拟接口测试；由于交付环境没有用户Token，尚未完成真实账号联网验收。首次真实运行后必须核对权限错误、字段变化、调用限额和返回数量，再允许调度器长期自动执行。
