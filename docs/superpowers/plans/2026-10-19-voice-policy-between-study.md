# VerbalVis Voice Policy Between Subjects Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. 用户已选择多个 GPT-5.6-Sol（medium）；同一文件仅一个 owner。复用子代理，不派生无关任务。

**Goal:** 支持 12 人、每人一题一种语音条件的组间研究，完成分配、真实语音、冻结、答案保存与审计闭环。

**Architecture:** 复用现有 revision_enabled/turn_taking、ResponseProtocol、五类工具和 Trace v2。StudyController 只增加研究阶段 gate，StudyStore 不获得图表提交权；render tracker 记录客户端渲染观测，不代表用户注意。

**Tech Stack:** 现有 Python 3.11、FastAPI、DuckDB、Vue、Pinia、Vega；新增存储使用标准库 SQLite，不新增服务或产品依赖。

**Spec:** [十二人语音组间实验设计](../specs/2026-10-19-voice-policy-between-study-design.md)。

状态：待用户审阅后实施。本文件是本研究的唯一当前实施清单，不另建逐代理进度文档。工作区为 C:/Users/admin/.codex/worktrees/visual-analysis-tools/VerbalVis，分支 codex/visual-analysis-tools。保留上一轮文档清理、已有任务池修改和其他独立工作的文件。

## Global Constraints

- 12 人/12 个计划正式 trial；两个条件各 6 人，两个任务在每条件各 3 人；每人只有一种条件，没有配对分析和交叉排程。
- 两组均语音，正式 WebSocket 不接受浏览器 text 分析；ASR 内部仍复用 accept_text。不增加 interaction_mode 或文字 Composer。
- 英文产品与参与者材料，中文作者说明；桌面 1920×1080 优先、1366×768 验证。
- exploration_limit_seconds=600，answer_limit_seconds=180，冻结准备总超时 15 秒，artifact 上限 50*1024*1024 字节，答案文本合计上限 8000 字符。
- ResponseProtocol 仍唯一授权源；commit guard 无 await/文件 I/O，不回滚以前合法提交，不用重跑查询伪造旧证据。
- 旧 pilot 与 Trace v2 原样兼容；新增 study journal schema_version=1，使用 session_id 与 v2 关联。
- 无新分析工具、鼠标 mutation/指代服务、原始音频存储、主分支合并或 GitHub 推送。
- 新目录 study_data/、study_schedules/、study_exports/ 加入 Git ignore；密钥/真实数据/参与者产物不提交。

## Review Focus

1. task 与 condition 混淆、重复参与或重试膨胀分母：Task 1/6 验证四个单元格各 3 与 assignment/attempt 分离。
2. turn-taking 在工具 follow-up 间或旧播放 ACK 后错误放行：Task 4 验证完整 request floor。
3. 截止与 commit/音频发送交错，已 commit 尚未发前端：Task 4 的同步 gate 和独立 frozen token。
4. 旧代/失败渲染及持久化失败却进入答题：Task 2/3/4 覆盖 15 秒与 evidence_ready。
5. 幂等冲突、刷新后重做、语义泄露及伪造条件：Task 1/2/4/6 覆盖拒绝和安全导出。

## 共享接口与所有权

| Owner | 文件 |
| --- | --- |
| A | backend/main.py、backend/realtime.py、新 backend/study.py；tests/test_study_runtime.py、tests/test_study_lifecycle.py，必要的既有 session/app 测试 |
| B | frontend/src/components/StudyPanel.vue、Dashboard.vue、ChartSlot.vue；composables/useWebSocket.js、stores/runtime.js、realtimePolicy.js；新 studyProtocol.js、dashboardRenderTracker.js；frontend/tests；新 backend/render_tracker.py、tests/test_render_tracker.py |
| C | 新 backend/study_manifest.py、study_store.py；experiments/olist_voice_policy_between_v1.json；scripts/prepare_study.py、audit_study.py、export_study.py；.gitignore；tests/test_study_schedule.py、test_study_store.py、test_study_audit.py、test_study_export.py、test_study_flows.py |
| 主代理 | 本设计/计划、README、PROGRESS、作者手册和冻结清单；审查、验证，不并发修改 A/B/C 文件 |

任务 1/2 由 C 顺序完成；B 可同时完成 Task 3 的前后端纯逻辑；A 先写 Task 4 接线测试并复用既有协议，待接口交付后整合。Task 5 属 B，Task 6 属 C，可在依赖完成后并行。提交按 owner 排队，仅显式路径；不把用户原有改动随手 git add -A。

所有研究控制消息为 {type, client_event_id, ...白名单字段}，ID 为 1–128 位安全 token。condition/participant/task/attempt/session 身份由 socket 的 server assignment 提供，消息传入身份或任意文件路径一律拒绝。相同 ID 同规范载荷重放回执，异载荷 conflict。PCM 帧不使用逐帧研究幂等登记。

服务端 init/dashboard_commit/trial.frozen 附 render={token,dashboard_revision,expected_views:[{view_id,view_revision}],reason}。view.rendered/view.render_failed 只允许 render_token、dashboard_revision、view_id、view_revision、render_generation、browser_duration_ms、presentation={mode,page_index} 和白名单 error_code；不接受任意图表 snapshot。

## Task 1 C 固定任务与分配

**Files:** 新 study_manifest.py、manifest、prepare_study.py、test_study_schedule.py；更新 test_study_flows.py 和 .gitignore。

**Interfaces:**
- validate_manifest(payload: dict) -> dict：校验 schema_version=1、design=between_subjects、study_version、两个规范条件、两任务、时限和同意要求。
- prepare_cohort(manifest: dict, participant_ids: list[str], seed: int) -> dict：返回 schema_version、algorithm_version、seed、manifest_sha256、assignments 和 balance。
- assignment 字段：assignment_id、participant_id、trial_id、task_id、condition、dataset_id、study_id、study_version、manifest_sha256、is_practice=false；attempt_id/session_id 在开始会话时生成，不在排程中重用。
- load_assignment(schedule_dir: Path, assignment_id: str, dataset_id: str) -> dict：只查配置目录内已校验排程，未知/重复/数据集不符拒绝；不拼接客户端路径。

- [ ] 写 test_balanced_single_trial_cohort：assert len(assignments)==12；每 participant 1 条；每 condition 6 条；每 task×condition 3 条；同 seed 相同结果。覆盖重复 ID、13 人、非法条件、未知任务、路径穿越和覆盖既有输出拒绝。
- [ ] 运行 .venv/Scripts/python.exe -m pytest tests/test_study_schedule.py -q，确认新增能力缺失 RED。
- [ ] 按设计 §3 两阶段随机分配实现，默认 seed=20261019，algorithm_version=task-block-randomization-v1；保存 Python 版本与排程规范 JSON 哈希。复制当前 pool 2.0 的英文材料，不改写其原文；逐任务哈希明确只对 prompt UTF-8 计算，manifest 哈希排除自身 hash 字段。
- [ ] 将旧 test_task_pool_has_six_open_ended_tasks 改为两任务 2.0 的 ID/title/范围/口径断言；保留 test_six_task_replay_uses_real_toolbox_state 原有六回放断言。已有 pool 文件由主代理单独审阅后纳入本任务，不回退为六题。
- [ ] 运行 Task 1 测试及 test_study_flows.py 全部 GREEN；只提交所属文件，记录新分配契约。

## Task 2 C 持久化与证据队列

**Files:** 新 study_store.py、test_study_store.py。

**Interfaces:**
- StudyStore(root: Path)；begin_attempt(assignment: dict, session_id: str, consent: dict, provenance: dict) -> dict，返回新 attempt_id 与 phase。
- apply_event(attempt_id: str, client_event_id: str, event_type: str, payload: dict) -> dict：短事务内登记幂等哈希、状态/答案/问卷变更及回执。
- append_event(attempt_id: str, event: str, metadata: dict, now_ns: int) -> None：白名单 study journal，带 seq/schema_version/session_id；不替代 Trace。
- enqueue_evidence(attempt_id: str, snapshot: dict, provenance: dict) -> str：同步深拷贝并入有界队列，不写磁盘；返回 job_id。
- async flush_evidence(attempt_id: str) -> None；evidence_ready(attempt_id: str, revision: int) -> bool；recover_incomplete() -> list[str]。后台 worker 为 study 所有，不随 response 取消。

- [ ] 写 test_answer_idempotency_and_conflict，断言相同 submission_id/内容只有一条答案、异内容不覆盖；test_evidence_refs_are_ready_and_attempt_local 拒绝外部/未落盘版本；test_completed_survives_disconnect 不反转终态。
- [ ] 加 test_evidence_quota_and_failure：恰好 50 MiB 可存、再多一字节 evidence_limit、写入异常不 ready；test_consent_categories_separate 未授权转写不泄露且已授权答案正常保存；test_restart_aborts_incomplete 保留所有旧记录。
- [ ] 运行 .venv/Scripts/python.exe -m pytest tests/test_study_store.py -q，确认 RED。
- [ ] SQLite 表至少包含 attempts、study_events、client_events、answer_drafts、answers、questionnaires、evidence_artifacts。答案先事务提交再 Saved；草稿版本递增；draft/submit 内容总长 8000；问卷只收 continuity/control/effort/waiting_interference 四项 1–7 整数，题项与锚点固定为设计 §5.2。写 artifact 使用同受控目录临时文件、原子替换、内容 hash 后登记，拒绝路径逃逸；队列/容量/写入故障可查询并由 A 中止 trial。
- [ ] 运行专项 GREEN，人工检查无 raw audio/自由日志拷贝；只提交所属文件。

## Task 3 B 真实渲染证明

**Files:** 新 render_tracker.py、dashboardRenderTracker.js 与对应测试；修改 ChartSlot.vue、Dashboard.vue、useWebSocket.js。

**Interfaces:**
- RenderTracker.register(attempt_id: str, snapshot: dict, reason: str) -> dict 返回共享 render envelope；冻结永远创建新 token。
- RenderTracker.ack(attempt_id: str, event: dict) -> dict 返回 {accepted,complete,failed,dashboard_revision,error_code}；token/expected views/generation 由服务器登记校验。
- 前端 ChartSlot emit rendered/render-failed；Dashboard 只转发当前 token 的组件事件。空面板用同类型 ACK 且 view_id/view_revision 为 null，只能在服务器 expected_views=[] 时接受。
- browser_duration_ms 仅浏览器本地 duration；不与 server monotonic 时间相减。

- [ ] 写 test_render_tracker_rejects_old_and_forged_ack：旧 token、错 attempt、未来 view revision 不完成当前集合；test_frozen_token_independent_of_commit、test_empty_dashboard_completes；覆盖重复 ACK 和 failed token。
- [ ] 写 frontend/tests/chartRenderLifecycle.test.js 与 dashboardRenderTracker.test.js：runAsync 完成前无 ACK；旧 generation 和卸载不报告；失败只发 error_code；空集合不等待；翻页只记录当前页。
- [ ] 运行后端专项与 frontend 的 npm test，确认相应 RED 后实现。每新 token 强制当前视图渲染，不做跨 token 缓存证明；保持全局尺度、现有分页和卡片位置。
- [ ] 运行后端专项、npm test、npm run build，GREEN 后提交所属文件。B 保留 useWebSocket 独占权供 Task 5 接线。

## Task 4 A 条件权威与单次任务生命周期

**Files:** 新 study.py、test_study_lifecycle.py、test_study_runtime.py；修改 main.py/realtime.py，必要时扩既有 session/app 测试。

**Interfaces:**
- StudyController(assignment: dict, attempt_id: str, store: StudyStore, render_tracker: RenderTracker, clock=monotonic_ns)。
- check_effect(kind: str, now_ns: int) -> bool：kind=input/commit/analysis_output，只读同步检查；非 exploring 或已到期 false。
- expire_if_due(now_ns: int) -> bool：同步关闭分析 gate，返回是否首次到期，不含磁盘/网络 I/O。
- freeze(snapshot: dict, last_rendered_revision: int | None, now_ns: int, reason: str) -> dict：生成冻结 snapshot/envelope 并记录待答题状态；不重新查询。
- handle_control(event: dict, now_ns: int) -> dict；poll(now_ns: int) -> list[dict] 驱动冻结等待、答案超时及持久化故障，只有 renderer 和 evidence 双 ready 后建立 answer deadline。
- AnalysisSession(..., study=None, render_tracker=None) 兼容旧构造。新增 async handle_study_event(event: dict)；非 study 旧路径不强制新消息字段。

- [ ] 写 test_assignment_blocks_condition_override 和 test_formal_browser_text_rejected；正式只认 assignment，拒绝伪造消息身份，ASR 不受浏览器 text 拒绝误伤。
- [ ] 写 test_turn_taking_waits_through_followup_and_final_playback：工具 response.done 后仍 busy，最终音频匹配 natural_end 才开放；旧 ACK 不开放。保留全双工 suspend/backchannel/analytical ASR 的既有回归。
- [ ] 写 test_deadline_blocks_commit_and_audio_dispatch，用可控 clock/barrier 在执行后提交前、锁等待后发送前及 ASR 返回前到期，断言无迟到 effect；test_committed_unsent_snapshot_can_freeze 验证新 token+完整 snapshot。
- [ ] 写 test_answer_deadline_starts_after_render_and_evidence、test_frozen_readiness_timeout_15s；test_no_restart_after_task_exposure；test_empty_answer_not_transport_failure。
- [ ] 运行新增专项 RED，再接线 Tasks 1–3。先验证 assignment/consent，再占单会话槽。ready 前不显示任务；trial.start 成功后进入 exploring。每次分析 effect 的资格检查与 protocol/CAS 保持同步；到期撤销未完成权限，随后在 guard 外持久化/发送控制消息。明确允许 provider 配置、既有构造阶段初始物化、init、研究状态、冻结/错误控制消息；添加 test_preparing_can_initialize_but_not_analyze，防止 gate 阻止初始渲染形成死锁，且不能把普通模型输出伪装为控制消息。
- [ ] provider 就绪初始化 snapshot 与每次合法 commit 都 enqueue_evidence，进入队列失败立即关闭 gate；不回滚已提交状态。冻结两个 ready 共享 15 秒总窗口。answer 超时落最近确认草稿，partial/empty 为 completed；实际失败为 aborted。
- [ ] 加 control.stop：两条件均可终止当前请求并停止播放，不产生新分析；普通麦克风暂停不冒充 Stop。正式无新 pointer mutation 入口。
- [ ] 运行 .venv/Scripts/python.exe -m pytest tests/test_study_lifecycle.py tests/test_study_runtime.py tests/test_session.py tests/test_protocol.py tests/test_app.py -q；GREEN 后只提交所属文件。

## Task 5 B 单任务研究界面

**Files:** 新 StudyPanel.vue、studyProtocol.js；修改 Dashboard.vue、useWebSocket.js、runtime.js、realtimePolicy.js；新增 frontend/tests/studyPanel.test.js、studyProtocol.test.js。

**Interfaces:** WebSocket 导出 sendStudyControl(type, payload)，type 仅 trial.start、answer.save、answer.submit、questionnaire.submit、control.stop、trial.task_presented 与渲染 ACK；trial.finish 不开放普通参与者 UI。trial.state 服务端发送 phase、freeze_status、remaining_ms、task（仅 start 后）、answer_status、evidence_refs_ready、allowed_actions。发送事件每次创建 client_event_id，重试复用原 ID 与原载荷。

- [ ] 写 test_single_trial_has_no_condition_switch：无切换/第二正式任务按钮；test_task_hidden_before_start；test_saved_only_after_server_receipt；test_disconnect_preserves_unsaved_text_without_restarting。
- [ ] 写 test_same_voice_ui_for_both_conditions：两组相同麦克风/Stop/图表面积，busy 提示只来自规范 policy；无文字分析 Composer。答题表单两组相同，冻结后只能查看证据与作答。
- [ ] 运行 frontend 的 npm test，确认 RED 后实现准备、开始、倒计时、冻结等待、答案、四题问卷。倒计时是 remaining_ms 的本地展示，不决定服务端期限；task_presented 仅客户端观测。断线停止，不自动创建第二次正式 session。
- [ ] 运行 npm test 与 npm run build。用明确 fixture 检查 1920×1080、1366×768 的真实卡片、heatmap、长文本、错误状态和答题；不以 fixture 声称真实语音可用。
- [ ] 提交所属文件，向 A 报告精确 wire 消息，无新接口命名分叉。

## Task 6 C 审计与安全导出

**Files:** 新 audit_study.py、export_study.py、test_study_audit.py、test_study_export.py；复用 analyze_traces.py 公开入口，不改 v2 语义。

**Interfaces:**
- audit_assignments(schedule: dict, attempts: list[dict], trace_summaries: list[dict]) -> dict：planned、started、completed、aborted、missing、diagnostics；唯一分母是 assignment，practice/attempt 单列。
- export_study(study_root: Path, output_dir: Path, *, package: str) -> dict：package=technical/ratings/process；独立白名单，默认拒绝覆盖。ratings 无 condition、transcript、延迟、直接身份；process 尊重 transcript 同意。

- [ ] 写 test_audit_counts_assignments_not_attempts，重复/缺失/condition不符/同人第二正式任务报诊断；题目暴露后重试不能变成另一个有效独立样本。有效 empty 与 aborted 缺失区分。
- [ ] 写 test_blinded_ratings_export、test_process_requires_transcript_consent、test_unready_or_cross_attempt_evidence_ref_rejected；未授权字段、路径和原始日志不得出现。
- [ ] 运行新增专项 RED 后实现；StudyStore 元数据与 v2 session 汇总做一致性校验，不把一个 session 拆成多个独立样本。对账时 expected 12/6/3，观察缺失则报告实际数量，不补零伪造效果。
- [ ] 运行专项及 tests/test_trace_analyzer.py、test_pilot_schedule.py、test_pilot_audit.py 回归 GREEN；只提交所属文件。现有统计脚本不用于冒充人工论证评分，自动推断语义/研究真值不在范围。

## 主代理验收与研究冻结

- [ ] 自查所有 Task 接口一致、文件无交叉写、用户原有改动保留；独立审查修复回给对应 owner。
- [ ] 完整 .venv/Scripts/python.exe -m pytest tests -q；frontend 的 npm test、npm run build；更新本轮实际结果。上一轮基线为 370 passed/1 task-pool 断言失败、frontend 90 passed，不能把它写成本轮通过。
- [ ] 用合成伪匿名 ID 执行 prepare_study --manifest experiments/olist_voice_policy_between_v1.json --participants 12 --seed 20261019 --output study_schedules/cohort.json；验证 12/6/3、覆盖保护和 hash。生成物不提交。
- [ ] 使用合成故障 fixture 运行 audit_study --schedule ... --study-data ... --strict 和三个 export package；并非正式采集结果。
- [ ] 两题×两条件做真实数据/真实 provider/实际浏览器预飞，检查模型、手动响应确认、follow-up、自然播放结束、回声、冻结与回收。缺凭证则报告未验证，不开始正式采集。
- [ ] 更新 README、作者手册、冻结清单和本计划勾选；评分 oracle、问卷文本及全会话编码规则在首位参与者前校准冻结。只用分配条件练习，无第二条件训练。
- [ ] 本地交付，不合并、不推送、不创建新中间报告；本计划的最终验收小节记录摘要即可。
