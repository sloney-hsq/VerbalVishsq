# Task 2：图卡与图表实现报告

日期：2026-10-19

## 实现内容

- 图卡头部改为标题、图表类型、声明的度量/单位、结果行数与观察单位的清晰层级；保留并重新排布既有 sampling、fixed scope、selection、shared order、independent scale、highlight 等语义徽标。
- 分析 warning / comparison suppression 继续使用可展开的真实说明；高基数 heatmap / horizontal bar 的分页区改为清楚的范围、页码、上一页、下一页和全部类别操作。
- `availableWidth` 仍表示整个图表工作区可用宽度。布局保持宽屏 3 列、中等 2 列、窄屏 1 列；facet、多系列折线和 X 类别较多的宽矩阵在可用时跨 2 列。X 类别少于 6 的 heatmap 在 4K 三列工作区使用单卡和有界内网格宽度；仅在中等窗口单卡不足 600px 时跨 2 列，避免 1366 宽度裁切。
- 绘图区高度、facet 尺寸、轴/图例字号、热力图行高和滚动上限根据实际卡片宽度分级。4K 卡片增大，1920/1366 与 Windows 缩放后较小 CSS viewport 仍维持可读尺寸。
- 长分类标签在密集竖向 bar 上按类别数、标签长度和卡片宽度条件旋转，并增加底部预算；`labelOverlap=false` 保留全部类别。固定宽 heatmap SVG 不再被 CSS 整体缩小，空间不足时由绘图区滚动，避免轴文字同步缩小。
- typed 与 legacy Vega-Lite spec 都消费相同的响应式 presentation；保留原数据、字段、返回顺序、显式 sort、全局色域、分页 value domain 与 selection semantics。
- 图卡和网格使用 `--vv-text`、`--vv-surface`、`--vv-muted`、`--vv-border`、`--vv-accent`、`--vv-gap` token，并均带 fallback；网格打包读取实际 CSS column gap，避免 token 改变后卡片行定位漂移。

## 修改文件

- `frontend/src/components/ChartSlot.vue`
- `frontend/src/chartLayout.js`
- `frontend/src/chartGrid.js`
- `frontend/src/chartGrid.css`
- `frontend/src/chartSpecs.js`
- `frontend/src/specFactory.js`
- `frontend/tests/chartSlot.test.js`
- `frontend/tests/chartLayout.test.js`
- `frontend/tests/chartGrid.test.js`
- `frontend/tests/visualSpecs.test.js`
- `frontend/tests/generalDataset.test.js`

## TDD 与验证

- RED：新增 4K span/plot/type scale、响应式滚动边界、图卡语义摘要/分页操作、typed spec 字号、legacy spec presentation 回归；首次运行 95 tests 中 5 个按预期失败。
- GREEN 专项：`node --test tests/chartLayout.test.js tests/chartGrid.test.js tests/chartSlot.test.js tests/visualSpecs.test.js tests/generalDataset.test.js` → 42/42 passed。
- 完整前端：`npm test` → 99/99 passed，0 failed。
- 生产构建：`npm run build` → exit 0，658 modules transformed。
- 静态检查：对 Task 2 所有权文件执行 `git diff --check -- <owned paths>` → 无输出。

## 未解决与验收边界

- 本子任务未做真实浏览器 viewport 截图/交互检查；3840×2160、2560×1440、1920×1080、1366×768 的最终组合验收属于 Task 3，需与主代理的 Dashboard/App/theme 改动一起检查。
- 构建仍报告既有 Vega embed chunk 833.94 kB / 超过 500 kB 警告；本轮没有改变 bundle 拆分策略。
- 未修改后端、分析数据、统计口径、dashboard revision、排序/尺度/选择逻辑，也未验证真实语音链路。
