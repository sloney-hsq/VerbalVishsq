# 用户实验分析工具与图表布局设计

日期：2026-10-16。状态：用户确认的实现范围已完成，离线与浏览器验收通过；真实语音实验预飞尚未执行。证据与边界见整合报告。

## 目标与交付边界

为 Olist 的六个开放探索任务提供足够的分析表达能力，并改善当前六类子图的布局，尤其是高类别数量热力图。用户可连续改变范围、统计口径和待检验解释；模型直接选工具与参数，不新增在线意图编码器。目标是可用于 pilot 的完整工具链和可操作界面，不承诺任意分析问题均能表达。

继续在 `codex/visual-analysis-tools` 隔离 worktree 工作，产品基线为 `e238557`。保留现有真实数据、旧接口、Education 适配器、响应撤销与原子提交协议。不得自动合并或推送。后端工具与前端由两个 GPT-5.6-Sol 代理分别承担，主代理整合契约和验收；不再新增实现代理。

本轮范围为增强 aggregate、compare_segments、distribution、relationship，新增 compare_periods，扩展共享筛选契约及按 ID 修改，优化 Vue 看板和离线示例。保留六种图形，不引入任意 SQL、任意公式、回归、因果推断、自动异常结论、新数据集自动理解或可拖动工作台。

两种备选方案是只使用已有工具，或扩展成通用统计平台。前者无法支持统计口径与时期比较等自然修订；后者超出实验需要。本设计采用用户确认的中间范围。

## 当前可运行实例与新增验收实例

现有 `scripts/check_visual_analysis.py` 使用真实 Olist 执行 15 步工具链；`frontend/scripts/renderVisualCheck.mjs` 将返回结果通过生产规格生成器输出六图。`http://127.0.0.1:8016/index.html` 是该离线展示，不是语音系统已通过真人验收的证据。

新增无密钥验收入口 `scripts/check_study_tools.py`，执行下述六个任务的确定性工具调用链，并导出真实结果与步骤记录。它不冒充模型选工具，不生成虚构语音或用户数据。前端示例复用生产布局与规格生成器，增加可点击的热力图分页和查看全图，不只提供截图。

Vue 主界面的真实语音入口继续使用原生产路径。实验前必须单独确认 provider、麦克风、扬声器、两种对话条件以及 Trace；离线回放和自动测试不能替代这些检查。

## 六个任务池

以下任务文字面向参与者；工程调用链只用于内部验收，不提供给参与者。任务允许得出证据不足或原假设不成立。

| ID | 参与者任务 | 主要能力 |
| --- | --- | --- |
| regional-delivery-risk | 找出一个订单量足够、值得优先调查的地区，用证据说明配送风险体现在哪里。 | 排名、样本门槛、均值与分位数、类别筛选 |
| delivery-period-change | 找出一段配送表现发生明显变化的时期，判断变化是否集中在某些地区或类别。 | 日周月趋势、时期对比、差值与百分点 |
| review-delivery-association | 调查低评分是否伴随配送问题，并寻找不符合这一解释的情况。 | 可调低分阈值、评分构成、分组对比 |
| freight-definition-robustness | 找出运费负担较高的商品类别，判断结论在不同统计口径下是否保持。 | 比例均值与总量比值、分布、固定基线 |
| freight-attribute-association | 调查运费差异与商品重量、体积、价格的关系，说明观察到的关系在哪些情况下不成立。 | 全量相关性、散点与二维分箱、分位数排除 |
| seller-delivery-stability | 在可比较的业务范围内找出值得调查的卖家，检查结论是否受订单量或极端订单影响。 | 卖家分组、订单去重、P90、范围与时期对照 |

新增版本化任务池 `experiments/olist_study_task_pool.json`，不覆盖已有两个任务的 `olist_pilot.json` 或既有参与者排程。任务池不是已经完成平衡分配的正式实验 manifest。先通过 pilot 检查任务难度、时长和实际修订机会，再固定分配、时限、排除规则与分析计划；不要求每人做完六项。

现有 revision_enabled 与 turn_taking 比较支持的是允许中途修订的效果。语音相对文字是否引发更多细微修改需要额外对照，不能由两个语音条件推出。修改次数需区分探索、误识别修复和系统错误修复；不将次数增加自动解释为收益。既有事后编码手册不被工具名称替代或静默改写。

## 基础统计契约

### 观测单位与有效性

本轮只使用现有 `order`、`item` 观测单位。order 按 order_id 去重，item 按 order_id 与 order_item_id 去重。按卖家或类别分组的订单在每组最多计一次，但可以属于多个组；返回跨组重叠提示，不能把组计数相加称为独立订单总体。不为此新增 seller_order 单位。

canonical review、有效配送时长、商品有效重量等继续服从注册表。动态统计不得绕过有效性规则。不同指标可以有不同有效分母，返回每行、每指标的有效数与公式。计数、均值、比例不能共用一个含糊的 denominator。

扩展语义版本，保留 dataset_id、旧参数与旧结果。新增 capabilities 描述可用 measure、筛选结构和比较方式；Education 未声明的能力不能被通用层强制加入。

### 稳定指标定义

aggregate、compare_segments、compare_periods 接受原 `metrics`，并新增 `measures`。两者至少提供一项，合计最多四个展示指标。出现 measures 时要求显式 `unit`。动态统计项有稳定 id，行与 columns 的列名始终使用该 id；修改定义不改变列身份。

id 为 1 至 64 字符的字母开头字母数字下划线标识，禁止双下划线；不得与分组、保留列、固定指标或其他 id 重名。双下划线专供派生对比列。

| 定义 | 参数 | 语义 |
| --- | --- | --- |
| mean / median | `{id, stat, field}` | 注册数值变量的有效观测摘要 |
| quantile | `{id, stat:"quantile", field, q}` | q 在 [0,1]，连续线性插值分位数 |
| threshold_ratio | `{id, stat:"threshold_ratio", field, op, value}` | 分子为有效观测中满足阈值者，分母为该字段全部有效观测 |
| registered_ratio | `{id, stat:"registered_ratio", formula_id}` | 仅预注册总量公式，首版为 `freight_share_of_total` |

threshold_ratio 的 op 限 eq、neq、gt、gte、lt、lte；value 必须满足字段类型。改变低分阈值不能改变分母总体。`freight_share_of_total` 在 item 单位上对 price、freight_value 均有效且总额为正的同一观测集合计算 `sum(freight_value)/sum(price+freight_value)`；不是逐项比例均值。公式注册表给出单位、分子、分母和有效条件。

空有效集合的 mean、median、quantile、ratio 返回 null，不返回 NaN/Infinity；分母为零的 ratio 返回 null。注册固定指标保持原有公式与空集行为。固定指标依其自身 grain 计算，动态 measures 依 unit 计算；metadata 标明各指标单位，不把混合口径冒充单一总体。

返回既有 rows/columns，以及 metadata.measure_definitions、每行有效计数、分母与缺失原因。sort、having、top_k.metric 可引用本请求的稳定 measure id 或固定指标。having 对未展示固定指标的现有支持保留。top_k 排名仍先在目标维度上完整计算，不平均其他分组的均值或比例。

## 五个分析工具

### aggregate

保留最多两个分组、固定 Top K 成员、完整结果校验。新增 measures 后仍返回 wide rows 和 result_kind=aggregate；例如 `{customer_state:"RJ", delivery_tail:25.1}`。`delivery_tail` 从 mean 改成 quantile 后仍是同一列。列元数据标明统计方式、单位与底层 source_field，但聚合值不可被 selection 当成原始行值筛选。

### compare_segments

复用 measures，保留旧 segment 格式和 wide rows，推荐显式 `{id,label,filters}`。新增 `comparison={reference_segment_id,outputs}`；outputs 是 difference、relative_difference、percentage_point_difference 的非空子集。

对每个展示指标 m 追加 `m__difference`、`m__relative_difference` 或 `m__percentage_point_difference` 列，原值仍保留。difference 为 v-ref；relative_difference 为 (v-ref)/abs(ref)，参考为零或任一无效时 null；百分点差为 100*(v-ref)，只适用于比例指标，单位 percentage_points，不能按 ratio 再乘百分数显示。

有 breakdown 时只配对同一分类键，不把不存在的参考组值猜成零。参考组与自身的合法差异为零；无效参考仍为 null。metadata 返回比较公式、缺参考原因、各组有效数及观测重叠，不默认输出显著性或置信区间。

归一化构成只允许注册表证明分类对该观测单位互斥、完备的计数分解。评分构成继续为有效 canonical review 的 1 至 5 档。首版还支持订单单位的 customer_state、order_status，以及 item 单位的 product_category；缺失分类必须作为单独缺失桶计入分母并披露。订单按商品类别的重叠分解不能归一化为总体构成。

### distribution

保留 histogram、box_summary，新增 `output:"quantiles"` 与 `quantiles:[q...]`，1 至 20 个唯一升序概率。输出 `{group?,quantile,value,valid_count,missing_count}`，result_kind=quantiles；quantile 为有序数值轴，可直接绘制折线或散点。不用截断的前端数据重新计算。

共享分位数筛选规则见下一节；所有分布输出均返回筛选前后有效数。直方图仍共享分箱边界，箱线图仍使用完整数据摘要，不改变既有统计定义。

### relationship

新增 `correlations:["pearson","spearman"]`，按需请求。points 与 binned_2d 的 rows 形状不变，metadata 返回整体和分组的相关统计；新增 `representation:"summary"` 返回可制图的 `{group?,valid_pair_count,missing_pair_count,pearson?,spearman?}`，result_kind=relationship_summary。

相关性在全部有效配对上计算，先于显示采样与分箱；Spearman 使用平均秩处理并列。小于两对或零方差返回 null 与原因；单独警告小样本，但不发明显著结论。整体按观测 ID 去重，分组可重叠时注明。summary 不接受 sampling/bins，不能用聚合均值相关冒充个体相关。分组结果不称为控制变量分析。

### compare_periods

新增 `{periods:[{id,label,start,end},...], time_field, output, grain?, group_by?, metrics?, measures?, unit?, filters?, comparison?}`。periods 恰两项，id 唯一、区间不重叠、均为 [start,end)。time_field 首版只支持注册原始 order_date；不把 order_month 等派生桶当原始过滤时间。comparison 使用 reference_period_id，差异公式与 segment 比较一致。

`output:"summary"` 对各完整指定区间汇总，可允许不等时长但必须返回各区间天数并显示不可直接等同暴露时长的提示；不自动日均化总数。`output:"series"` 必须提供 grain=day/week/month，边界对齐日、周一或月初，两期具有相同桶数；按 bucket_index 对齐而不是把两期不同日期错误合并。

结果为 wide rows，包含 period_id、period、请求分组及指标/差异列；series 额外有 bucket_index、bucket_start、bucket_end、bucket_present。result_kind=periods。绘图可用 bucket_index 为 X、period 为 color；tooltip 保留实际日期。

完整时间 spine 包含没有观测的桶；这些桶 bucket_present=false，所有指标列为 null，原始 record_count=0 单独记录。有效样本存在但阈值分子为零才形成真实零比例。差异仅在两侧相应值有效时计算。

metadata 返回基础数据的 observed_date_extent、请求区间、实际生效区间、日历边界、每组有观测桶/无观测桶及样本量。观测密度不是数据采集完整性：不得把每桶有记录命名为完整采集或公平比较。超出基础数据日期范围或被共享日期条件裁短时，默认保留原值、将差异置 null 并说明原因；不静默扩展共享范围。来源是原数据的无时区日期，按日历对齐，不套用运行机器时区。

本工具不接受局部 time_range，periods 是其局部时间参数；共享 filters 的日期限制仍相交并披露。summary/series 都支持同一 measures 契约，不能只在普通聚合中支持 P90 而时期比较又退回均值。

## 共享筛选和分位数范围

### 有界组合

保留 filters 数组的隐式 AND。元素可以是旧叶子，或 `{id,op:"or",branches:[{all:[leaf,...]},...]}`。最多 20 个顶层元素、每 OR 2 至 8 个分支、每分支最多 8 个叶子、总叶子最多 64 个；不允许其他嵌套或任意 NOT 表达式。这样能表达“RJ 的家具，或 SP 的电子商品”。

普通叶子继续使用注册字段、允许的运算符和参数绑定。order_status 仅允许顶层普通叶子；无显式状态时保持 delivered 默认。OR 中的状态条件明确报错，不猜测默认范围。共享、局部、segment 与选择条件始终取交集，OR 不能绕过共享限制。

订单级混合条件必须在统一查询计划中保留无商品订单可匹配的订单条件分支；不能一律 inner join。一个 AND 上下文内的商品条件由同一个商品项满足，不能用多个独立 EXISTS 让不同商品拼凑满足条件。最终按订单与分组键去重。所有分析工具共用此谓词计划，不复制五套语义。

### 分位数规则

在分析工具的局部 filters 中允许 `{id,field,op:"quantile_between",value:{lower?,upper?}}`。概率位于 [0,1]，双边界要求 lower<upper。仅可用于显式 unit 兼容的注册数值观测变量；不允许置于 OR、单个 segment 条件或共享 set_analysis_filters，以免混合观测单位或各组自行裁剪。

基础总体为完整共同范围与普通筛选后的数据，移除当前请求中的所有分位数规则。compare_segments 使用请求 segments 的并集，compare_periods 使用两时期的并集；总体按观测 ID 去重。分组、Top K、采样均不影响阈值。多条规则各自在同一基础总体上独立求值，再将物化边界 AND；禁止递归裁剪。边界包含，并列值可能使实际排除比例不等于名义比例。

返回每条规则的 q、实际数值边界、有效基础样本数、单规则排除数，以及全部规则合用后的保留数。无有效阈值返回 `EMPTY_REFERENCE_POPULATION`，不删除规则或扩大范围。

linked 视图随共同范围修改重新求阈值，metadata 标明基准范围与解析结果。snapshot fork 将当前阈值物化为普通数值条件，同时保留 materialized_from_quantile 来源说明；后续范围变化不能令固定基线漂移。复制后更改范围默认沿用固定阈值，只有用户重新指定分位数规则才重算。

## 修改与失败行为

analysis_patch 新增 `measure_changes={upsert?,remove?}`，按稳定 measure id 整项替换；未知删除、重复 ID、同 ID 同时删除与更新均报错。与 set.measures 冲突时拒绝。set/unset 的必需参数判断必须按源工具实际 schema 校验，不能继续硬编码 metrics 永远必需。

filter_changes 的稳定 ID 指向顶层叶子或 OR 组；修改 OR 内部时替换该组。执行前递归去掉配置 ID。replace_source 对旧普通叶子保持按字段的既有覆盖规则；OR 组按稳定 ID 显式替换，无相同 ID 的组保留并相交，不按内部字段拆组。不兼容的单位、变量或规则整次失败。

延续私有 draft、原子多图更新、过期响应拒绝、无变化不增加版本，以及撤销。仅视觉或分页改变不得重新查数据。新增错误至少包括 INVALID_MEASURE、INVALID_COMPARISON、INCOMPATIBLE_PERIODS、EMPTY_REFERENCE_POPULATION；所有错误有 code/message/path 与可行恢复建议，不提供误导性替代结果。

## 前端布局与热力图

### 看板与卡片

保持现有对话面板与麦克风流程，重做子图空间策略而非整个应用换皮。网格以实际看板可用宽度为依据：宽度至少 880px 时两列，每列约 420px 起；更窄为单列，不能只按窗口宽度判断而忽略侧栏。保留视图创建顺序，不使用 CSS dense 自动重排。

普通图为单列标准卡；多系列趋势、分面和高类别热力图在两列布局中占满一行。卡片取消统一 330 至 360px 高度，采用约 360/420/600px 的紧凑、标准、矩阵布局档位；高度由图形需求决定。标题允许两行，单位和关键提示可换行，辅助元数据可展开，不能挤掉标题与图例。

统一白底、低对比边框、12px 圆角、16px 间距，轴标签至少 11px，标题约 14px。保留现有稳定类别配色；数量/比率等连续色域按语义元数据选择顺序色，跨零差异可用以零为中心的发散色。未知字段不靠业务名猜测色义。

### 类别热力图

高类别数量不再默认渲染成超长细条。离散 Y 轴类别超过 24 个时启用每页 20 类，按完整类别域分页而非按 rows 切片，同类的所有 X 单元格必须在同一页。显示“第 1 页，共 4 页；1–20 / 72 类”、上一页、下一页和查看全图。末页禁用下一页；键盘可操作、状态可读。

默认行高约 22px、标签区最大 220px，长标签可省略但必须能查看完整值。色标置顶横向，长度随容器调整且上限约 280px；不在两列矩阵右侧留下大片空白。少量 X 类别填满剩余绘图区。大量 X 类别采用至少约 40px/列的内部水平滚动，不自动交换语义轴或产生页面级横向溢出。

查看全图保留完整行高并在最大约 560px 高的卡片绘图区滚动。二维连续 binned_2d 热力图绝不分页；保持全部箱与端点。缺失分类组合不自行填零，显式零频箱按返回值显示。

分页前从完整数据计算类别域、色域、元数据与高亮匹配；分页后只投影可见 marks。所有页使用完全相同色域，同一数值不能换页变色。类别顺序依次采用注册 sort_order、显式 visual/source sort、后端返回首次出现顺序；按指标排序必须尊重原排序语义，不能自行平均比例来排序。

页码与 paged/all 模式是 ChartSlot 的本地展示状态，不写入 view.data、后端 scope、dashboard digest 或 revision。数值更新但类别域不变时保留页码；类别变化时校验并收敛到有效页。选中类别位于其他页时给出中性提示，不取消选择、不自动跳页。页面翻动不作为分析修订计数。

### 其他图形与分面

条形图的类别数决定行高，长横向条形图允许卡内滚动，不裁数据。折线、散点、直方图、箱线图的标准绘图区约 300 至 320px，按卡片宽度安排刻度密度。图例允许顶部换行，不挤压到不可读。

分面桌面优先两列，窄屏一列，明确每个子图宽高；不继续将 facet 套用无效的 autosize fit。共享/独立尺度仍由已有 visual.scales.resolve 决定，展示独立尺度提示。分面维度、颜色和 selection 不能在重排中丢失。

createSpec 增加兼容的可选 presentation 参数；布局纯函数提供跨度、绘图区大小、分页信息和当前投影。后端数据与新统计信息通过通用 columns/metadata 消费，不增加 Olist 字段名分支。新 percentage_points、correlation 等单位须正确格式化，不能与 ratio 混淆。

### 离线示例与生产界面一致

renderVisualCheck 使用同一个布局函数和规格生成器。热力图跨整行，生成各页和全量 SVG，原生按钮切换，查看全图有明确滚动窗口。普通图保持响应式排列；heatmap.svg 为默认分页图，heatmap-full.svg 保留完整图，不将部分图标注为完整数据。

实际 Vue 应用同样通过浏览器检查，而不是仅检查静态 SVG。若工具环境无法完成真实浏览器验收，交付必须明确说明未完成项，不将编译成功称为可用性已验证。

## 模块与代理边界

后端代理拥有 datasets/olist、backend 的契约/patch/统计接入、Python 测试、工具回放脚本及实验任务池。新增统计定义、谓词计划、时期计算应分模块，不能继续堆进 interface.py。尽量让分位数与分组统计在 DuckDB 完成；必须在 Python 计算的全量相关/秩计算应测量耗时和内存，不以抽样代替精确统计。

前端代理拥有 frontend/src、frontend/tests、frontend/scripts，负责布局、规格、交互与示例渲染。双方先固定返回列、单位和 metadata；前端不得为了布局反向修改统计语义。README、正式设计、最终整合报告由主代理统一编辑，避免共享文件冲突。

## 验收与完成标准

1. 精确统计夹具覆盖一单多商品、多卖家、重复评价、无商品订单、空组、零分母、并列分位数、零方差。证明 OR 的同商品约束与订单去重；阈值比例使用未被分子条件裁剪的正确分母。
2. 同一 measure ID 从 mean 改成 P90，图表字段、having、排序与局部筛选保持一致。连续修改不会清除未提及条件，失败批次没有部分生效。
3. 分位数基于全部基础观测，多个规则不互相递归影响；分组/采样不改变阈值。snapshot 固定阈值，linked 范围变更重算并披露。
4. 时期对比覆盖等长序列、任意 summary、日周月、缺桶、超范围、共享日期裁剪、零基准、比例百分点、动态 P90；不能从无观测或日期范围推断完整采集。
5. Pearson/Spearman 在人工可核对夹具上精确正确；显示采样 seed/max_points 变化不改变统计。不同单位不被隐式合并，分组重叠被披露。
6. 六条任务链各含至少一次范围修订、口径/目标修订或解释对照，并检查未变条件、分母和最终状态。内部链是测试，不要求参与者照读。
7. 实际 72 类×2 州热力图默认四页，标签与色标可读，最后一页包含剩余类别；换页色域不变、全部类别可达、无查询或 revision；2D 分箱不分页。
8. 六类图、长标题、空数据、缺失值、分面、窗口 resize、跨页选择，在 360/768/1440px 视口检查无页面级横向溢出。按真实看板宽度检查对话侧栏占位。
9. Python 全量测试、前端全量测试和生产 build 通过，旧 Education 和初始看板兼容；真实 Olist 六任务回放与真实 Vue 图形验收留存证据。运行新鲜测试，不沿用基线通过数字。
10. 真语音 pilot 前通过 provider/设备与 trace strict 预飞，所有实验条件共用同一工具和布局版本；离线工具 demo、浏览器视觉验收、真人实验三种证据分别报告。

## 后续执行门槛

用户已确认本书面设计和执行安排。实施计划见 `../plans/2026-10-16-study-tools-and-chart-layout.md`；两个现有 GPT-5.6-Sol 代理按文件边界实现，主代理执行跨端验收。代码验收与真实语音实验预飞分别记录，不能互相替代。
