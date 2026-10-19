## Task 5 B 单任务研究界面

**Files:** 新 StudyPanel.vue、studyProtocol.js；修改 Dashboard.vue、useWebSocket.js、runtime.js、realtimePolicy.js；新增 frontend/tests/studyPanel.test.js、studyProtocol.test.js。

**Interfaces:** WebSocket 导出 sendStudyControl(type, payload)，type 仅 trial.start、answer.save、answer.submit、questionnaire.submit、control.stop、trial.task_presented 与渲染 ACK；trial.finish 不开放普通参与者 UI。trial.state 服务端发送 phase、freeze_status、remaining_ms、task（仅 start 后）、answer_status、evidence_refs_ready、allowed_actions。发送事件每次创建 client_event_id，重试复用原 ID 与原载荷。

- [ ] 写 test_single_trial_has_no_condition_switch：无切换/第二正式任务按钮；test_task_hidden_before_start；test_saved_only_after_server_receipt；test_disconnect_preserves_unsaved_text_without_restarting。
- [ ] 写 test_same_voice_ui_for_both_conditions：两组相同麦克风/Stop/图表面积，busy 提示只来自规范 policy；无文字分析 Composer。答题表单两组相同，冻结后只能查看证据与作答。
- [ ] 运行 frontend 的 npm test，确认 RED 后实现准备、开始、倒计时、冻结等待、答案、四题问卷。倒计时是 remaining_ms 的本地展示，不决定服务端期限；task_presented 仅客户端观测。断线停止，不自动创建第二次正式 session。
- [ ] 运行 npm test 与 npm run build。用明确 fixture 检查 1920×1080、1366×768 的真实卡片、heatmap、长文本、错误状态和答题；不以 fixture 声称真实语音可用。
- [ ] 提交所属文件，向 A 报告精确 wire 消息，无新接口命名分叉。

