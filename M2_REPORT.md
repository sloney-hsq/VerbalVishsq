# Milestone 2 验收报告：Visual Analytics Runtime

验收日期：2026-10-13。基线：已通过 M1 的 Olist Analytical Backend。

## 1. M2 解决什么

M1 解决“数据和指标是不是真的”，M2 解决“同一套数据语义能不能通用地进入图表与对话操作”。

本阶段没有新增 Olist-only 工具，也没有把初始图数据硬编码在前端。初始图与会话中的创建、修改、筛选使用同一条路径：

```text
Dataset interface
  → aggregate / compare_segments
  → columns metadata + rows
  → create_chart / update_chart / set_analysis_filters
  → private dashboard draft
  → one public revision
  → metadata-driven Vega-Lite spec
```

## 2. T16：Metadata → visualization

`frontend/src/specFactory.js` 使用每个查询结果的 `columns` 作为唯一字段元数据来源。

- `type` 决定 nominal / ordinal / quantitative / temporal encoding。
- `label` 生成 axis、legend 和 tooltip title。
- `unit` 决定格式：`ratio`、`BRL`、`days`、`points`、`kg`、`cm3` 和 count-like units。
- `description` 进入合法的 Vega-Lite 顶层 `description` 和 `usermeta.columns`，不写入不合法的 field definition。
- ratio 只在显示时使用 `.1%`，row 中的 `0.125` 仍保持数值。
- quantitative color 通过 `legend.format` 格式化，不会生成错误的 `color.axis`。
- metadata 缺失时拒绝猜测类型；`ChartSlot` 将错误显示为可见的 render failure。

筛选标签同时支持 `dimension_index`、分类 `dimensions` 和旧 `resources[*].fields`，并覆盖 `eq/neq/gte/lte/gt/lt/in/between/is_null`。

## 3. T17：移除 Olist 前端特判

- 删除 `ChartSlot.vue` 中的 `low_score_ratio` 阈值徽标。
- 原有 Vue 布局、图表卡片样式和视觉层级保留。
- `highlightSpec.js` 只保留 `x / series / color` 这类通用别名。
- 非结构化高亮值只会在 view x/color、实际 columns 和实际 row keys 中查找。
- `{field,value}` 与 `{x_value,series_value}` 合同保留。
- 多个 clause 不在同一 row 共现时返回 `null`，不显示虚假高亮徽标。

对 `frontend/src` 扫描以下领域字段无命中：

```text
low_score_ratio late_ratio order_week order_month order_date
product_category customer_state review_score
```

## 4. T18：初始 Dashboard 走正式工具链

`configs/olist.json` 中只保存五个普通 `create_chart` 参数，不保存 rows：

1. Monthly Orders Trend。
2. Average Review Score by State。
3. Orders by State。
4. Category Revenue (Top 15)。
5. Monthly Average Delivery Days。

`AnalysisSession` 构造时的严格顺序是：

```text
begin one draft
  → Toolbox.execute("create_chart", view 1, same draft)
  → ...
  → Toolbox.execute("create_chart", view 5, same draft)
  → commit once
```

任一图失败都会 discard 整个 draft；公开 dashboard 继续是 revision 0 且没有 partial views。WebSocket 会返回：

```json
{
  "type": "configuration_error",
  "code": "initial_dashboard_error",
  "message": "Initial dashboard view 3 failed: ...",
  "details": {"view_index": 3, "tool_error": {"code": "tool_error", "message": "..."}}
}
```

顶层配置不是 list 时也返回相同错误类型，`view_index` 为 `null`，不会误报为 Provider 连接失败。没有 `initial_dashboard` 的 Education 配置保持 revision 0。

## 5. 真实 Olist 物化结果

| View | Rows | X | Y | Unit | Truncated |
|---|---:|---|---|---|---|
| Monthly Orders Trend | 23 | order_month | order_count | orders | false |
| Average Review Score by State | 27 | customer_state | avg_review_score | points | false |
| Orders by State | 27 | customer_state | order_count | orders | false |
| Category Revenue (Top 15) | 15 | product_category | revenue | BRL | true |
| Monthly Average Delivery Days | 23 | order_month | avg_delivery_days | days | false |

月份视图数据升序，两个 state 视图按对应指标降序，Top-15 category revenue 恰好 15 行且降序。五个 view 的 `source_tool` 均为 `aggregate`，最终 dashboard revision 为 1。

## 6. 最终验证

```text
Python:   129 passed, 1 Starlette/httpx deprecation warning
Frontend: 44 passed, 0 failed
Build:    Vite production build succeeded, 653 modules transformed
Scan:     frontend forbidden Olist field scan clean
Review:   frontend and backend re-review passed with no remaining findings
```

Build 仍有 Vega embed chunk 大于 500 kB 的既有警告，不影响构建成功。当前环境没有 `DASHSCOPE_API_KEY`，因此上述证据不等于真实 Qwen 语音会话已联调。

## 7. M2 不包含什么

- 不修改 `backend/dashboard.py` 的事务语义。
- 不扩展 `backend/response_protocol.py`。
- 不新增 RAG、Redis、MCP、multi-agent 或复杂 planner。
- 不宣称 Agent 自主规划质量、用户效率或论文假设已被证明。

M2 证明的是：已有数据语义可以不经领域前端分支，通过同一工具链稳定地物化为可继续修改和筛选的 Dashboard。
