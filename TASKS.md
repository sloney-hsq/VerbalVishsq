# VerbalVis 单一主线任务看板

更新时间：2026-10-15。本轮以已批准的实现快照为唯一基线，不推倒重写。执行顺序固定为：**Olist Analytical Backend → Visual Analytics Runtime → Research System**。后一里程碑不得绕过前一里程碑的验收。

## Milestone 1：Analytical Backend

目标：不依赖语音、Agent 或前端，仅调用 Olist adapter 就能可重复地完成时间、地区、品类、评分、配送、seller 和销售分析。

| ID | 任务 | 验收标准 | 状态 |
|---|---|---|---|
| T00 | 固定基线 | Python / frontend 测试数量有记录；依赖可重建；生成物被 gitignore | 已完成（迁移前未误打 tag） |
| T01 | 读取 9 张 Olist 原始表 | 每张表可独立读取、有行数和必要字段校验 | 已完成 |
| T02 | 建立 canonical grains | order / item / payment / customer / seller×order 粒度明确 | 已完成 |
| T03 | 消除多表放大 | items、payments、reviews 先聚合再关联；收入和订单数手算回归 | 已完成 |
| T04 | 字段 registry | 时间、customer、product、seller、payment、order 分类；含 label/type/description/grain | 已完成 |
| T05 | 时间派生 | date / Monday-week / month / quarter / weekday / hour 及单测 | 已完成 |
| T06 | Sales metrics | order/item/customer counts，revenue/freight/total，AOV/item price | 已完成 |
| T07 | Review metrics | 每单唯一 canonical review；评分、低分、1/5 星、评论比率分母固定 | 已完成 |
| T08 | Delivery metrics | approval/dispatch/transit/delivery/promise/late 定义、缺失策略与单测 | 已完成 |
| T09 | Product/logistics metrics | weight/volume/freight ratio 的定义与可聚合结果 | 已完成（P1 提前落地） |
| T10 | Seller analytics | seller 分组复用通用指标，不新增 seller-specific tool | 已完成（P1 提前落地） |
| T11 | Payment analytics | 当前只保留 payment 粒度/维度；三项 payment metrics 在 M1 后再评估 | 部分完成 |
| T12 | Customer/repeat analytics | `customer_unique_id` grain 已建；repeat metrics 在 M1 后再评估 | 部分完成 |
| T13 | `aggregate` | 0/1 个 group-by、1–4 个 metrics，稳定 columns metadata | 已完成 |
| T14 | `compare_segments` | 多个显式 segment 使用共同 metrics/filter，返固定 `segment` 列 | 已完成 |
| T15 | Filters / sort / limit | 9 种白名单 operator，值参数绑定，time range 半开区间 | 已完成 |
| T23-D | Olist correctness | 对抗性 9-CSV fixture；Task A/B；revenue/order/review/late/weekly 回归 | 已完成 |

M1 退出条件：

1. `compare_commerce` 已从公开工具和回归测试中消失。
2. Task A（SP weekly）与 Task B（RJ 两品类）在 synthetic oracle 和真实 Olist 上通过。
3. 整个 Python 测试集通过，实际 Olist 查询的行数和指标记录在 `OLIST_ADAPTER_REPORT.md`。
4. `backend/dashboard.py` 和 `backend/response_protocol.py` 在 M1 不修改。

## Milestone 2：Visual Analytics Runtime（已完成）

| ID | 任务 | 完成标准 | 状态 |
|---|---|---|---|
| T16 | Metadata → visualization | 图表只依赖 columns metadata | 已完成 |
| T17 | 清除前端 Olist 特判 | 无 `order_week/customer_state/low_score_ratio` 领域分支 | 已完成 |
| T18 | Initial dashboard | 5 个初始视图全部由正式 dataset tool 生成 | 已完成 |

M2 退出条件：Agent 能用相同的 `aggregate/compare_segments + create/update/filter chart` 完成地区→周→评分→配送→seller 的连续可视探索。

M2 验收证据：

1. Olist 初始 5 图均通过 `Toolbox.execute("create_chart") → aggregate` 实际物化，共用一个私有 draft，只产生 revision 1。
2. 任一初始图失败时，整个 draft 被丢弃，WebSocket 返回结构化 `initial_dashboard_error`，不得误报为 Provider 连接错误。
3. 前端根据 `columns.type/label/unit/description` 生成 Vega-Lite spec；禁止 Olist 字段扫描无命中。
4. 原有 `create/update/set_analysis_filters` Olist 通用路径回归保留，没有增加 seller/review/delivery 专用图表工具。

## Milestone 3：Research System

| ID | 任务 | 完成标准 | 状态 |
|---|---|---|---|
| T19 | In-flight lifecycle | 精简的 request phase 与 in-flight revision 事件 | 已完成（独立 review 通过） |
| T20 | Execution / commit semantics | committed/read_only/superseded/conflicted/no_change 可区分 | 已完成（独立 review 通过） |
| T21 | 实验条件 | `turn_taking` vs `revision_enabled`，其余系统完全相同 | 已完成（独立 review 通过） |
| T22 | Experiment trace | participant/trial/task/condition + 完整时间线 | 已完成（独立 review 通过） |
| T23-R | Race tests | generating/querying/pre-commit/post-commit/late-old-result 时序 | 已完成（独立 review 通过） |
| T24 | Offline trace analysis | Trace v2 JSONL → deterministic trial-run metrics + diagnostics | 已完成（独立 review 通过） |

M3 软件退出条件已通过：同一分析任务的两种 canonical condition 共用数据/工具/模型/提示词；request lifecycle、执行/提交、前端反馈可追踪且 race tests 通过；离线分析器从 Trace v2 派生 trial-run metrics，并且 revision saving window 只有观察到对应旧 request 的 settled timestamp 才能计算，否则为 null。真实 Qwen 语音 pilot 与用户研究效果仍是外部验证项，未验证前不得声称已完成。

## Milestone 4：Pilot Readiness（软件材料已完成）

| ID | 任务 | 完成标准 | 状态 |
|---|---|---|---|
| P01 | Pilot task manifest | 两项开放式 Olist 任务，不规定固定工具顺序/答案 | 已完成 |
| P02 | Counterbalanced schedule | 四个显式序列平衡 task、condition 和先后顺序 | 已完成 |
| P03 | Session URL generator | 验证 token/manifest/base URL，拒绝非规范条件和意外覆盖 | 已完成 |
| P04 | Pilot runbook | 预飞、标准 trial、失败/重试、Trace 质检和 Go/No-Go 门槛 | 已完成 |
| P05 | Public-review hygiene | CI、忽略规则、contributing/security/release checklist | 已完成 |
| P06 | Pilot reconciliation | 排程与 Trace 批量对账，识别缺失、重复、错配、计划外和不完整 trial | 已完成 |
| P07 | Revision codebook | Goal/Scope/Hypothesis/Presentation 事后编码、排除与一致性流程 | 已完成 |
| P08 | Formal-study freeze checklist | 研究决策、版本身份、真实预飞、隐私、Go/No-Go 与冻结后变更控制 | 已完成（待研究团队逐项签署） |

M4 只表示实验运行材料与自动化已具备。由于当前环境没有真实凭证和参与者，provider 预飞、pilot 观察、伦理审批、许可证选择与正式研究冻结仍是人类责任，不得标记为已完成实验。

## M3 非目标

不做 RAG、MCP、multi-agent runtime、Redis、复杂 planner、semantic rollback、任意 CSV 自动理解、复杂 intent classifier，以及没有必要的 `backend/dashboard.py` / `backend/response_protocol.py` 功能扩展。

## 已知外部限制

- 当前环境无 `DASHSCOPE_API_KEY`，真实 Qwen 语音联调不能由单元测试替代。
- 归档源工作区的广泛测试曾有两个与缺失 `extract_verbalvis_cases.py` 相关的既有失败；它们不归因于本仓库实现。
- 迁移前历史记录：源工作区未发布、未推送或创建干净 Git tag；独立仓库的 tag 和远程状态以当前 Git 记录为准。
