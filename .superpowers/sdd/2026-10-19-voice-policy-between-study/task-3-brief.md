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

