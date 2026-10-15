# Visual Analysis Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user requests exactly one implementation subagent, model `gpt-6-sol`, reasoning effort `medium`; do not spawn further agents. The parent reviews and verifies the finished changes.

**Goal:** 实现支持 Olist 配送风险和运费负担探索的四类分析工具、六种图形，以及局部修改、复制和显式选择联动。

**Architecture:** 复用现有 DatasetAdapter、参数化 SQL、Toolbox 和原子 draft。数据集模块负责粒度与统计，通用后端负责视觉契约与状态，前端将有类型的结果转换成 Vega-Lite；不加入意图分类器。

**Tech Stack:** Python 3.11、DuckDB、jsonschema、pytest；现有 Vue、Vega-Lite、Node 测试和 Vite。保持当前依赖版本范围，不为本次功能增加框架。

**Spec:** `docs/superpowers/specs/2026-10-15-visual-analysis-tools-design.md`。

## Global Constraints

- 模型直接选择工具和参数；不增加意图分类器。
- 图形包括 bar、line、scatter、heatmap、histogram、boxplot；分组、堆叠、归一化堆叠和分面作为视觉配置。
- 分布与关系分析属于本次范围，不推迟为可选附加能力。
- 第一版筛选列表只支持 AND，集合条件由 in 表示，多个独立人群由 segments 表示。
- 后端统计使用完整有效数据；只有 points 允许明确、可复现的采样。
- 旧工具调用、初始看板、旧视图快照和教育适配器必须继续工作。
- 不修改原始 CSV，不调用真实语音服务，不访问密钥，不推送 GitHub。
- 使用一个 `gpt-6-sol`、`medium` 子代理；通过文件交接，修复复用同一代理，主代理最终审查。

## Review Focus

1. 一张订单含多个商品、支付和评价时，订单级分布与评分分母不能膨胀；Task 2 的重复观测测试覆盖。
2. 全空、单值、零值和最大边界不能导致非法坐标、丢计数或伪造零比例；Task 2 和 Task 4 覆盖。
3. 只改图形或时间粒度时不能丢地区条件；同名变量与指标不能混淆；Task 3 覆盖。
4. 旧图选择到达时目标可能已改变；要拒绝失效来源，不能部分筛选后提交；Task 4 覆盖。
5. 初始图、教育适配器、旧工具 schema 与非电商字段不得因扩展失败；Task 3 至 Task 5 覆盖。

## 执行方式和工作目录

先由用户审阅本计划并选择工作目录，然后派遣一个子代理连续完成 Task 1 至 Task 5。优先在用户同意的隔离 worktree 中执行；若用户选择当前目录，在非 main 功能分支实施。只创建一个实现分支，不自动合并或推送。

子代理首次读取本计划与 spec，随后按任务定位代码；不要整仓扫描或反复重读规格。每个任务先运行定向测试，最终再执行完整回归。已有 `.venv`、前端依赖和数据可以复用，但必须确认 Python 包实际导入路径指向实施工作区，不能误测主检出目录。

在计划相邻的 `2026-10-15-visual-analysis-tools-progress.md` 中记录任务完成状态、提交、测试命令及结果。最后写 `2026-10-15-visual-analysis-tools-report.md`，只向主代理返回状态、提交范围、测试摘要和未解决项。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| datasets/olist/schema.py、metrics.py | 字段、观测单位、指标和分母注册 |
| datasets/olist/query_common.py | 有类型过滤、条件编译、观测源与结果元数据 |
| datasets/olist/queries.py | 汇总和条件组比较 |
| datasets/olist/distributions.py、relationships.py | 完整数据分布和配对关系 |
| datasets/olist/interface.py | schema 发布、能力描述、执行分派 |
| backend/analytics.py | 旧表格与新增结果契约校验 |
| backend/chart_contract.py、chart_patch.py | 视觉校验、旧格式归一化、增量修改 |
| backend/selection.py | 选择验证、输出字段到源谓词的映射 |
| backend/tools.py、dashboard.py、realtime.py | 调用、作用域、版本、历史、批次错误 |
| frontend/src/chartSpecs.js、specFactory.js | 六类图形编译与旧快照兼容 |
| frontend/src/highlightSpec.js、stores/dashboard.js、components/ChartSlot.vue | 有效选择显示、焦点、图形呈现 |
| backend/prompts.py | 当前能力与语音局部修改指引 |

文件拆分仅限上述职责，不做无关重构。可复用已有帮助函数，不为满足文件表机械复制逻辑。

### Task 1 字段与结果契约

**Files:** 修改 `datasets/olist/schema.py`、`metrics.py`、`interface.py`、`backend/analytics.py`；新增 `datasets/olist/query_common.py`、`tests/test_analysis_contract.py`；复用 `tests/test_olist_adapter.py` 的合成数据。

**Interfaces:** `normalize_filters(filters: list, field_index: dict) -> list` 负责验证与规范化；`compile_filters(filters: list, field_index: dict) -> tuple[list[str], list]` 仅返回白名单 SQL 片段和绑定值。接口类 describe() 增加 field_index；结果增加 result_kind 和 metadata，保留原有字段。

- [ ] 写失败测试：`test_filter_types_and_boundaries` 断言 in 数组通过、标量 in 失败、布尔数值失败、无效日期失败、between 两端包含。`test_observation_registry` 断言 order 不接受 product_weight_kg 数值轴，item 接受；注册三个有效订单计数指标。`test_result_contract_legacy_and_typed` 断言旧表格继续有效、错误箱线列和非有限数被拒绝。
- [ ] 运行 `.venv/Scripts/python.exe -m pytest tests/test_analysis_contract.py -q`，确认新增能力缺失导致失败，而非导入配置错误。
- [ ] 实现上述函数和注册信息；保留 canonical review、非负配送时长及 delivered 默认规则。让 shared/local filters 共用同一校验，兼容旧 dimension_index/resources.fields。
- [ ] 重跑定向测试及 `tests/test_datasets.py`、`tests/test_olist_adapter.py`，全部通过。
- [ ] 只提交本任务文件，提交说明 `feat: define typed analysis and filter contracts`，记录测试结果。

### Task 2 四类分析计算

**Files:** 修改 `datasets/olist/queries.py`、`interface.py`；新增 `distributions.py`、`relationships.py`、`tests/test_olist_visual_queries.py`。需要共享夹具时使用专门测试帮助模块，避免复制大型 CSV 夹具。

**Interfaces:** 保留 `build_aggregate(arguments, scope, dimension_index, metric_index)` 的返回形式；扩展 `build_segments`。新增 `execute_distribution(con, arguments: dict, scope: list | None, registry: dict) -> dict` 和 `execute_relationship(con, arguments: dict, scope: list | None, registry: dict) -> dict`，返回规范成功结果主体，由 interface 补 dataset_version。

- [ ] 写失败测试：`test_two_dimensions_having_and_fixed_top_k` 核对二维分组、未展示指标的 having 和跨时间固定成员。`test_segment_score_composition` 断言每组 1 至 5 档齐全、非空组 share 总和为 1、空组 share 为 null。`test_order_distribution_deduplicates_items` 断言一单多商品只贡献一次。对 `[1,2,3,4,100]` 断言 Q1=2、median=3、Q3=4、上下须=1/4、outlier_count=1。直方图验证最大端点、显式边界外计数、常量及空样本。
- [ ] 写关系失败测试：确定性采样相同 seed 得到相同 observation_id；缺失一轴时不进入有效配对；二维箱计数之和等于完整有效配对数；商品项价格与运费不误取订单总额。测试组数、点数、分箱数上限和全部边界错误。
- [ ] 运行 `.venv/Scripts/python.exe -m pytest tests/test_olist_visual_queries.py -q`，确认新能力测试失败；实现四工具的 schema、参数化查询和元数据。使用 DuckDB 完整数据求分位数及分箱，不把全量原始行发送给前端。严格采用 spec 中 20 默认分箱、30 分布组上限、12 关系组上限、2000 默认点数及 5000 点上限。
- [ ] 运行本任务测试、Task 1 测试及旧 Olist 测试，全部通过；检查现有指标值与分母未改变。
- [ ] 提交 `feat: add distribution relationship and richer aggregate queries`，记录测试结果与新增语义。

### Task 3 图表工具与状态

**Files:** 新增 `backend/chart_contract.py`、`chart_patch.py`、`tests/test_visual_tools.py`；修改 `tools.py`、`dashboard.py`、`realtime.py`、`prompts.py` 及相应现有测试。

**Interfaces:** `normalize_visual(config: dict) -> dict` 接受单一新格式或旧格式；`validate_visual(visual: dict, result: dict) -> dict` 返回规范视觉配置。`apply_analysis_patch(source: dict, patch: dict, filter_ids: dict) -> dict` 保留省略字段；`apply_visual_patch(visual: dict, patch: dict) -> dict` 仅接受 spec 路径。Toolbox 新增 `_fork_chart(args, draft)`，现有创建与更新方法使用上述帮助函数。

- [ ] 写失败测试：`test_legacy_chart_and_typed_source` 验证旧调用兼容与注册工具 schema。`test_visual_only_update_does_not_query` 用计数适配器断言仅改标题、排序不增加查询次数。`test_patch_preserves_region_when_switching_week` 断言地区、时间范围不变；删除未知筛选 ID 报错。`test_switch_to_box_requires_distribution` 拒绝平均值改箱线图。
- [ ] 写复制与版本失败测试：snapshot 固定原图及副本范围，linked 随共享筛选变化；复制失败不留空图；no-op 不增版本；纯高亮不占分析撤销项；撤销清理不存在视图的焦点。批次失败保留失败路径，其他调用标识回滚或未执行。
- [ ] 运行 `.venv/Scripts/python.exe -m pytest tests/test_visual_tools.py -q` 确认失败，随后实现 create/update/fork、active_view_id、view_revision、scope_mode 及分析历史。补全 inspect_dashboard 摘要与有界数据读取，避免每次将全图数据发给模型。
- [ ] 运行本任务、`tests/test_dashboard_tools.py`、`tests/test_initial_dashboard.py`、`tests/test_protocol.py`、`tests/test_session.py`；更新测试时只改变明确的新契约，不能删掉旧行为的实质断言。
- [ ] 提交 `feat: add typed chart editing cloning and analysis history`。

### Task 4 六种图形和显式选择

**Files:** 新增 `frontend/src/chartSpecs.js`、`frontend/tests/visualSpecs.test.js`、`backend/selection.py`、`tests/test_visual_selection.py`；修改 `specFactory.js`、`highlightSpec.js`、`stores/dashboard.js`、`components/ChartSlot.vue`、`backend/tools.py` 和相关投影代码。

**Interfaces:** 前端 `buildChartSpec(view) -> object` 根据规范 visual、result_kind、columns、metadata 分派；保留外部 `createSpec(view, highlightElement)`。后端 `resolve_selection(source_view: dict, predicate: list, effect: str) -> list` 验证实际来源标记并映射注册字段；Toolbox 新增 `_set_selection(args, draft)`。

- [ ] 写失败测试：六种规格可经现有 Vega-Lite compile 编译并以 Vega View 渲染 SVG；box_summary 使用 q1/median/q3/须图层而非再聚合；直方图设置起止边界；评分色序固定；分组 bar 不默认堆叠；share 不二次归一化。测试空数据、单值箱线、log 非正值、分面上限、量化 color 和 size。
- [ ] 写选择失败测试：热力图类别对变为两个 AND 条件，时间桶和分箱映射正确边界；无匹配、未知字段、过期 source_revision 和不兼容目标全量拒绝；重复来源替换条件，clear 只移除该来源条件；来源修改不级联；删除来源保留可清除的筛选标签。
- [ ] 运行 `node --test tests/visualSpecs.test.js`（frontend 工作目录）和 `.venv/Scripts/python.exe -m pytest tests/test_visual_selection.py -q`（仓库根目录），确认新增行为失败；实现图形分派与一次性联动，不增加持续图依赖网络。
- [ ] 运行 frontend 全部测试及 Task 3、Task 4 后端测试，确认旧快照、教育字段、纯高亮无查询和多目标失败回滚均通过。
- [ ] 提交 `feat: render six chart types and link explicit selections`。

### Task 5 完整场景与交付

**Files:** 新增 `tests/test_visual_analysis_flows.py`、`scripts/check_visual_analysis.py`；按需更新 `README.md` 的工具能力部分；写实施报告及进度记录。

**Interfaces:** 冒烟脚本从现有配置加载受信任适配器，执行 spec 两条场景，输出每步工具名、成功状态、样本数、数据缩减信息和耗时。不包含 API 密钥，不发送语音，不修改 CSV。

- [ ] 先写场景测试：配送排名→having→SP/RJ 月趋势→周趋势→分布→热力图选择→评分构成；运费排名→分布→散点→二维箱→换价格轴→RJ 副本→筛选→撤销。每一步断言有效条件、观测单位、结果和已提交状态，不只断言 success。
- [ ] 增加运行层交错测试：旧查询晚到不得覆盖新视图；取消后无部分提交；新图创建加 activate 不需要未知 ID 的第二个同批调用。运行定向测试，修复实际集成缺口。
- [ ] 执行完整 `.venv/Scripts/python.exe -m pytest -q`，frontend 的 `npm test` 与 `npm run build`，记录新鲜结果。确认 Python 导入与前端测试都使用实施目录。
- [ ] 用现有真实 Olist 数据执行冒烟脚本；对条形、折线、热力、直方、箱线、散点各渲染一个代表样本进行视觉检查，检查轴、图例、分母提示、空数据和长类别标签。保存必要报告而非大量原始数据或生成图片到 Git。
- [ ] 提交经过验证的场景测试与文档。子代理自查 diff 与 spec，列出未实现或未验证项，不能以已有测试通过代替全部需求覆盖。父代理审查后，修复仍交回同一个子代理；不自动 push 或 merge。

## 审查检查表

- [ ] Task 1 的字段与结果契约被 Task 2、Task 3、Task 4 使用，无第二套相互矛盾的字段表。
- [ ] Task 2 的结果列名、result_kind 与 Task 4 渲染映射完全一致。
- [ ] Task 3 的选择筛选容器、作用域及版本被 Task 4 联动和 Task 5 撤销测试覆盖。
- [ ] 五项 Review Focus 各有定向断言，而非只靠端到端 success。
- [ ] 旧三类图、旧工具、教育适配器及初始看板未退化。
- [ ] 最终说明区分本地验证与真实模型工具选择表现。
