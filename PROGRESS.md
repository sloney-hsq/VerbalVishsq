# Execution ledger — plan: IMPLEMENTATION.md

2026-10-12: User requested code completion after confirming dataset + interface scope. Executing the approved TASKS.md; IMPLEMENTATION.md records exact integration decisions, not a new project scope.

Ruling: work in the explicitly requested repository on the approved research snapshot; do not create a separate worktree or alter archived source. Existing extraction-script test failures remain separately reported.

| Shared boundary | Producer / consumer | Resolution |
|---|---|---|
| Task 1 → Task 2 | DatasetAdapter definitions/execute → Toolbox | dict result + columns metadata, trusted read-only adapter operations |
| Task 2 → Task 3 | Draft + commit → AnalysisSession | commit is synchronous; protocol guard held; no await |
| Task 1 → Task 3 | description/tools → prompts/session | generated descriptions, no domain conditionals |
| Task 2 → Task 4 | view snapshot → renderer | old view keys retained, columns metadata added |
| Task 3 → Task 4 | browser events | existing event names retained, sequenced input floor |
| All tasks | source ownership | only the approved implementation, no shared edits by implementers |

Task 1: complete, uncommitted; 23 scoped tests. Independent review findings (module lifetime, typed scalar/temporal cells) fixed and re-review clean.
Task 2: implemented; 28 scoped tests. Review found empty-dashboard date-filter value validation gap; assigned integration fix wave.
Task 3: implemented; reviewer found suspension during post-commit sends and failed/empty ASR policy gaps. Fix wave also covers late utterance correlation and under-lock effect validation.
Task 4: implemented. Frontend test/build and app HTTP/startup verified. Trace setup slot leak and ASGI cancellation cleanup fixed with regressions.
Task 5: execution/commit outcome contract and race tests complete; independent review approved. Live provider/human interaction not verified.

Ruling: dataset descriptor uses `version` as in DESIGN_ZH; tool results and dashboard snapshots use `dataset_version`. This is an explicit boundary mapping, not two versions.

Ruling: Qwen manual-response controls are required and must be echoed as false in session.updated. Official server examples include these keys, but client docs do not promise all models accept them. Unsupported endpoints fail closed instead of silently assigning automatic responses new authority. Live provider compatibility remains unverified until credentialed integration.

Task 3 progress: 6 protocol + 6 session + 2 trace/prompt tests pass; real WebSocket entry being integrated. No live Qwen validation yet.

2026-10-13 integration evidence before final fix wave: 70 new Python tests passed; frontend 34 tests/build passed (additional presentation tests subsequently added). App health, dataset metadata, static homepage: HTTP success; component style blocks identical to old source. Browser tool failed to initialize (kernel asset path missing), so no screenshot comparison claimed. Process environment DASHSCOPE_API_KEY absent (presence checked only, no secrets read).

Review coordination: dataset_implementation → data_contract_review (fixed/review clean); dashboard_tools → state_tools_review (one fix assigned); session/main → runtime_transport_review (concrete fixes assigned). integration_fixes owns only runtime/tools and associated regressions; the coordinating scope owns frontend/main/docs. Existing unrelated user files remain untouched.

Ruling: tests may use transport doubles to deterministically inject races; production always connects real Qwen and never substitutes fake responses. A green test suite does not establish live provider compatibility.

## 2026-10-13：开发主线收敛为三个 Milestone

用户明确要求停止同时扩展 protocol、dataset 与实验。`TASKS.md` 现在是唯一任务主线：M1 Analytical Backend → M2 Visual Analytics Runtime → M3 Research System。M1 期间冻结 `backend/dashboard.py` 和 `backend/response_protocol.py` 的功能扩展。

M1 当前证据：

- Olist adapter 拆为 `interface.py / schema.py / metrics.py / queries.py`；
- 9 张 raw tables 可独立读取；
- persisted `order_grain / item_grain / payment_grain / customer_grain / seller_order_grain`；
- canonical latest review 规则统一用于所有 review metrics；
- 公开数据集工具仅 `aggregate` 和 `compare_segments`；
- 旧 `compare_commerce` 测试调用已迁移；
- focused Olist tests：24 passed；
- full Python tests：121 passed / 1 既有 deprecation warning；
- frontend baseline：36 passed；production build 成功（仅 Vega bundle size warning）；
- 真实 Task A：SP weekly 27 rows / 15,495 orders；
- 真实 Task B：RJ office_furniture 212 orders vs bed_bath_table 1,357 orders。

迁移前历史记录：源工作区未创建 Git tag 或推送；独立仓库的 tag 和远程状态以当前 Git 记录为准。

## 2026-10-13：M2 Visual Analytics Runtime

- `specFactory.js` 现在只从 result `columns` 元数据获取 field type、label、unit 和 description；ratio/BRL/days/points/kg/cm3/count 采用通用格式规则，原始数值不被转成字符串。
- column description 保存在合法的 Vega-Lite 顶层 `description` / `usermeta`，不再写入非法 field definition；quantitative color 格式使用 legend。
- `highlightSpec.js` 只保留 x/series/color 通用别名，根据实际 columns/data 推断；不存在的 clause 组合不显示虚假高亮徽标。
- `ChartSlot.vue` 移除 low-score 阈值特判，样式和布局保持；metadata/spec 错误进入可见错误边界。
- Olist `initial_dashboard` 含 5 个普通 `create_chart` 参数，没有 rows。`AnalysisSession` 用同一 draft 执行 5 次正式 `create_chart → aggregate`，成功后只 commit 一次；失败整体 discard。
- 真实 Olist 验收：5 图行数 23/27/27/15/23，单位为 orders/points/orders/BRL/days，月份升序，Top 15 revenue 降序且 `truncated=true`。
- 最终测试数以本轮最后验证命令为准；真实 Qwen 仍因缺少 `DASHSCOPE_API_KEY` 未验证。

## 2026-10-14：M3 Task 6 离线分析器与整合验证

- 新增标准库 Trace v2 analyzer：按 session 独立汇总，输入按物理行容错、按 session-local `seq` 排序；报告坏 JSON、schema/context/timing 错误、重排、gap、重复与冲突。
- 指标只用 ID、canonical lifecycle/outcome、真实 dashboard commit 和 monotonic timestamps；consent-controlled transcript/arguments/audio/payload 不读入分析投影，也不回显。
- `revision_saving_window_ms` 仅使用实际观察到的 `previous_request_id` settled timestamp 计算；缺失、superseded、只有 `response.done` 或负差均返回 null，负差仅增加 diagnostic。
- analyzer 专项测试：44 passed；完整 Python：277 passed（1 个既有 Starlette/httpx deprecation warning）；frontend：63 passed；production build 成功（既有 833.94 kB embed chunk warning）。
- CLI fixture 输出为 1 个 session run、2 requests、1 个真实 dashboard commit、duration 1000 ms、last-request terminal latency 100 ms、0 diagnostics；真实 Olist initial-dashboard smoke：1 passed，使用配置的 9 CSV 数据目录。
- 完整命令、坏输入恢复与 review 状态记录在 `.superpowers/sdd/m3-research-system/reports/task-6-offline-analysis-verification-report.md`。
- Task 6 独立 review 发现并修复了跨 batch 复用 `call_id` 导致 superseded call 少计的 P2 问题；现以 `(batch_id, call_id)` 为自然键，最终复审通过。M3 软件实现已完成；带凭证的 Qwen 语音 pilot 与用户实验仍是外部验证边界。

## 2026-10-14：M4 Pilot Readiness

- `experiments/olist_pilot.json` 固定两项开放式探索任务和 S1–S4 四个交叉平衡序列；任务文本不进入 URL 或隐藏模型上下文。
- `scripts/prepare_pilot.py` 校验 manifest、规范 condition、伪匿名 token 与 base URL，为每个 trial 生成与 Trace v2 context 一致的 URL；默认拒绝覆盖既有排程。
- `PILOT_RUNBOOK.md` 固定预飞、标准 trial、失败/重试、每日 strict Trace 质检和 pilot Go/No-Go 边界。
- 新增 GitHub Actions、发布忽略规则、`CONTRIBUTING.md`、`SECURITY.md` 与 `RELEASE_CHECKLIST.md`。许可证、真实作者 citation、数据分发权和伦理材料仍需维护者明确决定，不由代码伪造。
- Pilot 排程专项回归：14 passed；完整 Python：291 passed（1 个既有 Starlette/httpx deprecation warning）；frontend：64 passed；production build 成功（既有 833.94 kB Vega embed chunk warning）。S1–S4 均成功生成排程，Trace fixture 在 `--strict` 下为 1 trial / 0 diagnostics，release hygiene checks 通过。最终独立复审发现并验证修复了 page URL 实验 context 未进入 WebSocket 和 practice/formal trial 共享 session 的两项 Important 问题；复审结论 `APPROVED`。

## 2026-10-15：Pilot evidence reconciliation

- 新增 `scripts/audit_pilot.py`：以 `(participant_id, trial_id)` 为自然键，将生成排程与 Trace v2 的隐私安全离线摘要对账；检测缺失、重复、context 错配、计划外、不完整、无已接受请求和无最终状态的正式 trial。
- Practice session 仅单独计数，不参与正式 trial 完成率；审计输出不复制 prompt、URL、transcript、tool arguments、audio 或原始事件。`--strict` 对任一诊断返回非零，输出文件默认拒绝覆盖。
- 新增 `REVISION_CODEBOOK.md`：人工只对已接受的 in-flight revision 编 Goal、Scope、Hypothesis、Presentation 或 Unclear；Trace 继续提供 phase、authority、commit 与 timing 事实，语义编码不进入在线控制路径。
- 新增 `STUDY_FREEZE_CHECKLIST.md`，将研究决策、版本身份、真实环境预飞、隐私、Pilot Go/No-Go 与冻结后变更控制分开列出；代码不能替研究团队勾选伦理、样本量和统计方案。
- `PILOT_RUNBOOK.md`、README、任务看板和发布检查表已接入批量审计与 codebook 冻结要求。
- 最终验证：Python 296 passed（1 个既有 Starlette/httpx deprecation warning）；frontend 64 passed；production build 成功（既有 833.94 kB Vega embed chunk warning）；审计相关专项 62 passed；Trace fixture `--strict` 为 1 trial / 0 diagnostics；S1–S4 均生成 2 个 trial；脚本编译和敏感产物/真实 Olist 数据忽略规则通过。
