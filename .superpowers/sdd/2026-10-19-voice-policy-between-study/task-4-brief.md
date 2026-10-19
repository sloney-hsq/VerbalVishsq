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

