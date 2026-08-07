# 全市场 AI 投资研究 OS

这是一个可运行的全市场投资研究系统原型。它把长期研究状态保存在数据库中，由确定性程序负责数据处理、异常检测、财务计算和状态迁移，由可替换的AI模型负责产业推理、公司研究和反方审查。Codex、Claude Code及其他MCP客户端读取的是同一套证据和研究状态，不依赖某一次聊天记忆。

当前版本为 **v0.3 real-data connector prototype**。研究软件链路已经完整跑通，但由于没有用户的正式数据授权，交付包内使用明确标记的合成DEMO数据，不能直接用于真实投资决策。逐项功能和缺口见 [`FEATURE_AUDIT.md`](FEATURE_AUDIT.md)。

## 已实现的研究闭环

```text
全市场产业指标异常 ─┐
                    ├→ 产业验证 → 公司量化映射 → 利润驱动树
公司订单/利润异常 ──┘                 ↓
                         悲观/基准/乐观盈利模型
                                      ↓
                         市场隐含增长与预期差
                                      ↓
                         独立反方审查与候选判断
                                      ↓
                         持续监控、削弱、证伪、报告
```

主要能力：

- 40个一级行业和跨行业主题，行业与指标由数据文件驱动，不写死在研究代码里；
- 市场驱动和公司驱动两条机会发现入口；
- 异常强度、趋势持续性和多指标同步检测；
- 原始文档、指标观测、数据期间、内容哈希和证据来源追溯；
- 事实、管理层表述、第三方数据、媒体线索和AI推断分级；
- 独立证据路径交叉验证；
- 公司业务纯度、利润弹性、负债、现金流和估值量化排序；
- 持久化利润驱动树；
- 悲观、基准、乐观三情景模型及不可覆盖的假设修订历史；
- 当前价格隐含的EPS增长要求反推；
- 产业研究、公司研究、反方审查和候选判断Agent；
- 可重复运行的研究状态机、逻辑削弱监控和异常队列；
- 每日/每周研究简报、预测快照和后续评价接口；
- FastAPI、静态浏览器面板、定时循环和MCP Server；
- OpenAI、Anthropic、双模型复核和无密钥离线模式；
- CSV/JSONL和通用授权HTTP数据连接器；
- 无券商下单接口。

## 启动

使用Docker：

```bash
cp .env.example .env
docker compose up --build
```

启动后访问：

- 研究面板：`http://localhost:8000/ui/`
- API文档：`http://localhost:8000/docs`
- MCP：`http://localhost:8001/mcp`

本地Python模式：

```bash
make bootstrap
make dev-backend
# 另开终端
make dev-mcp
```

## 验证

```bash
make test
curl -X POST http://localhost:8000/api/research/run-cycle
curl -X POST http://localhost:8000/api/research/run-cycle
curl http://localhost:8000/api/dashboard
```

测试覆盖连续两次研究周期，确保系统不会像原版一样在第二次运行时因状态回退而失败。

## 接入真实数据

项目已加入 Tushare Pro 官方HTTP连接器和自动同步命令，覆盖全A证券主数据、申万一级行业、每日行情估值、财务增量、业绩预告和业绩快报。详细步骤见 [`docs/real-data-integration.md`](docs/real-data-integration.md)。

```bash
# .env 中配置 TUSHARE_TOKEN，并关闭演示数据
PYTHONPATH=backend python -m app.cli sync-tushare \
  --trade-date 20260803 \
  --announcement-date 20260804

# 后续增量同步可跳过主数据
PYTHONPATH=backend python -m app.cli sync-tushare --skip-master
```

原有CSV/JSONL和通用HTTP连接器仍然保留：

```bash
PYTHONPATH=backend python -m app.cli ingest-csv /path/to/export
PYTHONPATH=backend python -m app.cli ingest-http https://your-data-gateway --token xxx
```

真实公告PDF仍需申请CNINFO/深证信授权数据服务后接入。

## Codex与Claude Code

项目已包含：

- `AGENTS.md`：Codex工程与研究规则；
- `CLAUDE.md`：Claude Code规则；
- `.codex/config.toml`与`.mcp.json`：共用MCP配置；
- `skills/investment-research/SKILL.md`：研究工作流。

MCP工具覆盖市场扫描、公司搜索、同行比较、证据与原文检索、利润树、公司三情景模型、假设修订、市场隐含增长、异常队列、报告和状态管理。

## 真实边界

当前尚未内置真实全A公司全集、具体数据商账号、稳定PDF表格与页码解析、全部细分行业特有指标、真实一致预期、完整历史回放校准、用户权限和生产运维。任何宣称“只需要填密钥即可直接实盘使用”都不准确。
