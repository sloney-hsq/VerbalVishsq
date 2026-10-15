# Olist 多图可视分析工具设计

状态：待用户审阅。日期：2026-10-15。

本次扩展让 VerbalVis 围绕配送风险和运费负担生成排名、趋势、分布、关系与构成视图，并支持语音讨论中的局部修改、保留基线和跨图选择。模型直接选择工具和参数；不增加意图分类器。本文定义待实现接口，不表示这些能力已经存在。

## 目标与范围

配送风险任务包括州延迟率排名、按周或月比较趋势、配送天数分布、州与商品类别交叉分析、准时与延迟订单的评分构成。运费任务包括类别运费占比排名、占比分布、重量或价格与运费的个体关系、类别与收货地区交叉分析，以及限定条件后的卖家比较。

保留现有 DatasetAdapter、受信任的数据集查询、私有 dashboard draft 和版本检查。扩展 aggregate、compare_segments、create_chart、update_chart，新增 distribution、relationship、fork_chart、set_selection。describe_dataset、set_analysis_filters、highlight_chart、inspect_dashboard、delete_chart、undo_dashboard 继续存在。

图形包括 bar、line、scatter、heatmap、histogram、boxplot；分组、堆叠、归一化堆叠和分面作为视觉配置。分布与关系分析属于本次范围，不推迟为可选附加能力。地图、任意 SQL、任意 Vega 表达式、自动回归或因果推断、任意双向持续联动、意图编码不在范围内。

## 当前实现与兼容边界

backend/tools.py 使用 source 指向数据集工具，当前图形为 bar、line、scatter；修改 source 会整体替换嵌套参数。datasets/olist/interface.py 发布 aggregate 与 compare_segments；aggregate 最多一个分组。frontend/src/specFactory.js 根据列元数据生成 Vega-Lite 规格。

保留旧 aggregate 的 group_by、sort、limit 和时间字段别名，不新增同义的 dimensions 或 order_by 参数。保留旧 compare_segments 的直接维度条件形式，通过兼容适配转为条件组。旧 create_chart/update_chart 的 chart_type、x、y、series 继续可调用，转换为规范 visual；新旧视觉参数不得在同一次调用中混用。

模型可见 schema 引导使用新接口；服务端保留旧接口校验与转换，已有测试和初始看板继续工作。前端能读取旧视图快照，将旧字段归一化成 visual。教育数据集仍只发布自己实现的分析工具，不能被强制要求支持 Olist 新能力。

## 数据和过滤契约

### 字段与观测单位

数据集描述增加统一 field_index，声明 type、label、unit、grain、groupable、filterable、allowed_ops、允许的观测单位及物理表达式的受信任映射。旧 dimension_index 和 resources.fields 保留兼容读取路径；通用代码不包含 Olist 字段分支。

Olist 为新分析工具注册以下变量。变量与聚合指标属于不同命名空间，例如 item 观测下的 freight_value 是单个商品项运费，而 aggregate 的 freight_value 是合计运费。

| 观测单位 | 变量 | 有效性规则 |
| --- | --- | --- |
| order | delivery_days、approval_days、dispatch_days、transit_days | 使用现有有效时间端点及非负时长规则 |
| order | review_score | 每单一个 canonical review，非空且在 1 至 5 内 |
| order | is_late | 可判定时为 0 或 1，其他为 null |
| item | price、freight_value | 数值非空；零值保留 |
| item | product_weight_kg、product_volume_cm3 | 原始尺寸或重量有效且为正 |
| item | freight_ratio | price 与 freight_value 非空且和大于零 |

order 以 order_id 去重，item 以 order_id 与 order_item_id 为稳定键。订单级分布与关系允许商品条件通过半连接限定订单，但不能通过普通连接重复订单。按商品类别分组的订单可同时属于不同组；返回 overlaps_across_groups 提醒不可相加。第一版 order 关系分析不允许把商品项变量当作订单变量；不自动猜测求和或均值。item 的数值轴只使用注册商品项变量。

### 筛选和时间

Filter 为 {field, op, value}，op 支持 eq、neq、gt、gte、lt、lte、in、between、is_null、is_not_null。in 要求非空同类型标量数组；between 要求升序两个端点且两端包含；空值谓词不接受 value。兼容旧 eq null 与 neq null，并归一化为空值谓词。所有数字有限，布尔值不能充当数值；日期必须可解析。

第一版筛选列表只支持 AND，集合条件由 in 表示，多个独立人群由 segments 表示。time_range 保留 {field, start, end}，至少一个边界，start 包含、end 不包含；双边界要求 start 小于 end。周起点为周一。时间粒度使用现有 order_date、order_week、order_month、order_quarter 分组字段，不新增冲突的 time_grain 参数。

共享、视图局部和选择筛选求交集。未显式指定 order_status 时沿用 delivered 默认范围；结果声明该默认。明确矛盾的条件返回 FILTER_CONFLICT，不自动覆盖。普通有效查询的零结果返回成功空结果，区别于冲突。

### 指标与有效样本

保留现有指标公式，增加 reviewed_order_count、valid_delivery_order_count、late_eligible_order_count 供 having 使用。每个请求指标返回分母定义与对应的有效数量，不以统一 order_count 代替所有指标分母。

revenue 不含运费；avg_freight_ratio 是商品项占比均值；avg_late_days 只计算延迟订单。类别筛选后的 avg_order_value 必须说明是所选商品金额除以相关订单数。mean 和 ratio 的空组返回 null，计数空组返回零。阶段均值默认分组展示，不将不同有效样本上的均值堆成总配送时长。

## 四个分析工具

### aggregate

参数保留 group_by、metrics、filters、time_range、sort、limit，新增 having 与 top_k。group_by 长度为 0 至 2，metrics 为 1 至 4。having 使用指标条件列表，运算符为 eq、neq、gt、gte、lt、lte、between；允许引用未展示的注册指标，服务端计算后仅用于过滤。

top_k 为 {dimension, metric, k, direction}，k 为 1 至 50，dimension 必须是请求分组之一。执行顺序为原始筛选、全时间范围按目标维度计算排名、选择固定成员、按请求分组重新汇总、having、排序。相同排名按规范维度值稳定打破并列。返回所选成员和排名范围；不自动添加 Other。

无 top_k 时不隐式选组。limit 保留现有最大 500；只读查询可返回 truncated=true。创建或更新视图不得把截断的表格解释为完整趋势、热力图或百分比，须返回 RESULT_TOO_LARGE，建议缩小范围、减少组数或使用 top_k。

输出 result_kind=aggregate，包含请求分组和指标列及样本数元数据。原有一维查询结果保持兼容。

### compare_segments

新组格式为 {id, label, filters}，id 必须唯一，组数 2 至 20。保留旧格式并按输入位置生成稳定兼容 ID。通用 filters 与 time_range 应用于每组；组筛选不能移除共享条件。

新增 breakdown：最多一个注册类别或有序字段。新增 normalization，取 none 或 within_segment，默认 none。不实现全体归一化，避免重叠组引入不明确分母。

within_segment 要求单一可加计数指标和互斥、完备的 breakdown 分类。评分构成使用 reviewed_order_count 和 review_score，分母是该组有效评分订单数。生成 1 至 5 全部档位，无记录档位为零；整组分母为零时 share=null。其他字段只有注册表声明满足互斥、完备条件时才能归一化。

输出 result_kind=segments，包含 segment_id、segment、breakdown、请求指标；归一化时另有 share 和 segment_denominator。返回组间观测重叠计数及计数所用单位，不能把重叠组之和称为总体。各组独立计算比例，绝不平均组比例来推算总体。

### distribution

参数为 unit、field、group_by、filters、time_range、output、bins。unit 为 order 或 item；group_by 最多一个适用类别字段；output 为 histogram 或 box_summary。bins 仅适用于 histogram。

bins 接受以下三种互斥形式：{edges:[...]}、{step:number}、{count:integer}。edges 为严格递增有限数，区间数最多 100；step 为正；count 为 1 至 100，默认 20。自动边界从所有比较组的有效数据共同确定，不能每组独立分箱。区间左闭右开，最后一个区间包含最大端点。常量数据合并为一个含该值的有限宽度箱；无有效值则 rows=[] 并返回有效数为零。

显式边界之外的有效数据计入 underflow_count 与 overflow_count，不丢失且不纳入常规箱；proportion 的分母仍为该组全部有效观测。每组输出相同箱边界和零频箱。结果行字段为 group（如有）、bin_start、bin_end、count、proportion。result_kind=histogram。

box_summary 使用连续分位数 Q1、median、Q3；须为落在 Q1-1.5*IQR 与 Q3+1.5*IQR 范围内的最小及最大实际值。输出每组 q1、median、q3、whisker_low、whisker_high、valid_count、missing_count、outlier_count。单个有效值的五个位置相等。空组不绘制箱体；显示零有效数。第一版不绘制异常值点，仅显示完整数据的异常值数量，避免抽样点误导。result_kind=box_summary。

样本数、分位数和直方图均基于完整筛选数据，不基于前端截断或点采样。默认组数上限 30、结果行上限 5000，超限返回 RESULT_TOO_LARGE，不静默删组。

### relationship

参数为 unit、x、y、group_by、filters、time_range、representation、sampling、bins。unit 为 order 或 item，x/y 必须是在该单位上兼容的注册数值变量。第一版 group_by 最多一个类别维度，最多 12 组。

representation 为 points 或 binned_2d。仅两轴都有效的配对参与计算，返回 eligible_count、valid_pair_count、missing_pair_count 及各组计数。不得把个体关系自动改为均值关系。

points 默认最多 2000 个点，硬上限 5000。sampling 为 {max_points, seed}；按稳定观测键与 seed 的确定性散列选择，返回方法、seed、实际点数和 sampled 标志。多个组共享总预算，默认不宣称各组等额抽样；需要密度比较时推荐 binned_2d。结果有 observation_id、x_value、y_value 和 group（如有），不返回与图无关的原始字段。result_kind=points。

binned_2d 基于完整有效配对计算；bins={x_count,y_count}，各轴 1 至 50，默认 20。所有组共享完整有效数据范围，使用与直方图一致的边界和常量规则。结果为 x_bin_start、x_bin_end、y_bin_start、y_bin_end、count、group（如有），result_kind=binned_2d。空格明确表示零频，不与缺失值混淆。采样参数不能用于此模式。

## 分析结果与错误契约

延续 success、dataset_version、rows、columns、truncated。新结果增加 result_kind 与 metadata；表格单元格仍为标量。metadata 包含观测单位、有效条件、有效样本统计、分母映射、分箱或抽样信息、重叠警告。columns 每列仍声明 nominal、ordinal、quantitative、temporal 之一，并可声明 semantic_role 与 source_field。

数据集适配器验证新增元数据及 result_kind 对应列契约。未声明 result_kind 的旧结果按普通表格处理，仅允许原有三类图，不猜测其为分布摘要。

错误保留 code、message、path，可附合法候选和恢复建议。至少区分 INVALID_FILTER_VALUE、FILTER_CONFLICT、INCOMPATIBLE_GRAIN、INCOMPATIBLE_ENCODING、RESULT_TOO_LARGE、INVALID_SELECTION、STALE_SOURCE_VIEW。批次失败保留实际失败调用的原始错误，其他调用分别标记 rolled_back 或 skipped，不将所有原因覆盖为一个 batch_rolled_back。

## 视觉规格与渲染

### create_chart

新形式为 {source, visual, title?, activate?}。source={tool, arguments}；tool 只能是当前数据集注册的只读工具，arguments 必须按该工具 schema 校验。schema 按注册工具生成受约束的分支，不接受任意工具名或任意表达式。

visual={type, encoding, stack?, sort?, scales?}。encoding 的 x、y、color、size、facet 为可选字段引用，tooltip 为字段数组；各类型进一步限定必需通道。type 取 bar、line、scatter、heatmap、histogram、boxplot。sort={field,direction}；scales 的 x/y 只支持 linear、log，默认 linear；log 要求所有绘制值为正，失败时拒绝而非静默丢点。类别标识在同一会话使用稳定配色，顺序型评分遵循 1 至 5 的顺序。

| 类型 | 结果与编码校验 |
| --- | --- |
| bar | 一类别轴及一数值轴；color 可用于分组或堆叠 |
| line | 有序时间或序数 X，数值 Y；不按 Y 大小重排时间 |
| scatter | 数值 X/Y；points 的字段引用映射 x_value/y_value，汇总点须标明分组单位 |
| heatmap | 两维度加数值 color；binned_2d 映射两轴的起止边界 |
| histogram | 必须为 histogram 结果；映射 bin_start/bin_end 和 count 或 proportion |
| boxplot | 必须为 box_summary 结果；将逻辑变量映射到四分位数和须字段 |

visual.encoding 引用逻辑分布变量时，服务端通过 metadata 映射实际列；普通表格不允许虚构列引用。size 仅支持散点、非负数值。facet 只支持一个离散维度，最多 12 面板；同指标同单位分面默认共享数值尺度，可显式 scales.resolve=independent 并显示提示。跨独立视图不自动锁定尺度，保留单独视图范围；复制视图的视觉参数初始一致。

stack 取 none、zero、normalize，只用于 bar 且需 color。none 使用并排分组；zero 要求指标对堆叠类别可加；normalize 要求结果携带有效分母与可归一化契约。already-normalized share 用普通 zero 堆叠和百分比轴，不二次归一化。均值、不同分母比例不可堆叠。

后端保存规范 source、visual、result_kind、metadata、columns 和 data。activate 默认为 true，写入 active_view_id；它是指代焦点，不等于筛选或高亮。图表显示单位、有效范围、抽样或截断警告；tooltip 带相关分母。前端从类型分派到小型渲染函数，箱线图使用摘要图层，禁止再对摘要求四分位数。

### update_chart

新形式为 {view_id, analysis_patch?, visual_patch?, title?}。同工具修改时 analysis_patch={set?, unset?, filter_changes?}；set 替换明确列出的顶层工具参数，未列参数不变；列表整体替换，不隐式追加。unset 只移除可选参数。相同路径不能同时 set 和 unset。

filter_changes={upsert?,remove?} 使用稳定筛选 ID。旧无 ID 筛选在视图规范化时生成 ID 并返回；ID 属于视图配置，执行查询时去除。未提到的条件保留。upsert 同 ID 为替换，remove 未知 ID 报错。

切换分析工具使用 analysis_patch={replace_source, inherit_scope:true}，与 set/unset/filter_changes 互斥。replace_source 必须提供完整工具特有参数；inherit_scope 复制原视图有效的局部筛选及 time_range，遇到新工具不支持的字段则报错。调用者明确提供同字段条件可替换继承的局部条件，但不能移除共享条件。不是通用递归 JSON 合并。

visual_patch={set?,unset?} 仅支持白名单路径，例如 type、encoding.x、encoding.y、encoding.color、encoding.facet、sort、stack、scales.x。换分析方法后必须校验完整视图，不兼容则整次失败。类型改变可以复用兼容数据，例如 aggregate 的 line 与 bar；改为箱线图必须更换 source 为 distribution。

仅视觉、标题变化复用完整已存结果，不执行数据库查询。source 参数或有效筛选变化才重查。无实际变化不增加版本或撤销记录。成功返回 changed_fields、effective_source、view_revision 与视图；提交状态由运行层在提交后补充，不提前声称已生效。

### fork_chart

形式为 {view_id, analysis_patch?, visual_patch?, title?, scope_mode?}。默认 scope_mode=snapshot：固定原图当前有效范围，将共享筛选物化为原图和副本的范围，使二者不受后续共享修改影响；副本应用修改，原图数值和视觉保持不变。该范围模式变化与副本创建是一次可撤销事务。元数据明确标记固定范围，避免用户误认为全局筛选仍会影响它们。

显式 scope_mode=linked 时不改变原图，副本继续继承共享筛选。不会混合两种解释。未改变分析参数的副本可复用数据；ID 独立。失败不留下空副本。

## 跨图选择与看板状态

set_selection 形式为 {source_view_id, source_revision, predicate?, target_view_ids, effect}，effect 为 highlight、filter、clear。source_revision 来自 inspect_dashboard 返回的 view_revision，防止把旧图上的选择应用于新语义。target_view_ids 必须非空、唯一；第一版禁止将来源图同时作为目标。

predicate 是输出字段或通道引用组成的 AND 条件，只接受来源结果中可验证的类别、时间区间或数值范围。来源选取必须匹配实际显示标记；无匹配返回 INVALID_SELECTION。对另一图应用筛选时，通过 source_field 映射回注册原始字段：时间桶变成左闭右开时间范围，分箱变成相同边界约定的区间，热力图单元格变成两个维度条件。排名指标值或聚合均值不能冒充原始行谓词。

highlight 不查询数据，只更新目标图的有效标记选择；不能表达对应标记的目标返回 INCOMPATIBLE_ENCODING，不丢弃部分条件。filter 使用来源视图 ID 作为目标图选择筛选的稳定键，重复调用替换同来源选择，多个来源取交集；返回生效条件及匹配数。clear 只清除指定来源在指定目标上的高亮和选择筛选，保留用户局部条件。

选择是一次性快照应用，不创建持续订阅或递归级联。来源图后续修改不自动重发选择；目标保留当时的规范条件及来源标签。删除来源图保留已应用的筛选并标为来源已移除，用户仍可从目标筛选列表清除；删除目标清理它的选择记录。

Dashboard 增加 active_view_id、各视图 view_revision、scope_mode 和 selection 状态。继续使用私有 draft 原子提交和现有过期响应权限检查，不增加数据库并行执行承诺。每次分析或视觉配置提交进入撤销历史；纯焦点和高亮不占分析撤销项。撤销时恢复分析状态并修剪失效焦点和选择，不回滚到引用不存在视图的高亮。undo_dashboard 在一个批次中必须是唯一工具调用。

旧 highlight_chart 适配为当前单图高亮，条件仍需全部验证。全局筛选只重算 linked 视图；一个失败则全部回滚。inspect_dashboard 默认返回摘要、视图版本、来源及筛选 ID，新增 view_id 和 include_data 可选参数；数据读取有上限并明确截断。

## 两条验收场景

### 配送风险

1. 按州查询 late_ratio 与 late_eligible_order_count，创建排序条形图。
2. 使用 having 排除少于 100 个可判定订单的州，保持其他条件。
3. 比较 SP 与 RJ 的月趋势，再将分组替换为 order_week，地区和时间范围不变。
4. 保留趋势图并创建两个州的配送天数箱线图和共享边界直方图。
5. 创建州与类别延迟率热力图，选择一个单元格筛选分布图。
6. 按 is_late=0 与 is_late=1 比较 review_score 构成；每组有效评分比例之和为 1，零分母组除外。

### 运费负担

1. 创建类别 avg_freight_ratio 排名，并按 order_count 做聚合后筛选。
2. 选定类别，生成 item 粒度 freight_ratio 箱线图。
3. 生成 product_weight_kg 与 freight_value 的散点图，并切换完整数据二维分箱图。
4. 将 X 改为 price；保留类别、地区及时间条件，明确仍为 item 粒度。
5. 复制图表为 RJ 范围，原图继续作为固定基线。
6. 排除超重商品后撤销，检查范围、统计值和图形恢复；纯高亮不成为撤销目标。

## 模块边界与验证要求

datasets/olist/schema.py 与 metrics.py 定义注册语义；queries.py 保留汇总与比较编译；新的分布与关系查询分别放在独立模块，复用过滤和粒度校验，不能复制多套语义。interface.py 负责发布 schema 和分派。backend/analytics.py 验证扩展结果契约；backend/tools.py 将视觉校验、补丁处理和选择转换拆成可独立测试的帮助模块。backend/dashboard.py 管理版本和历史，backend/realtime.py 保留错误并控制提交。前端按图形类型拆分规格生成，沿用列元数据和现有看板投影。

测试要求如下，实施时按先失败测试再实现的顺序进行。

- Olist 合成夹具：一单多商品、多支付、多评价、跨类别订单、空组、单值组、负或缺失时长、零价格和缺失重量。对分母、去重、分位数、上下须、区间边界和重叠组给出精确断言。
- 分布：所有组边界相同，箱内计数加范围外计数等于有效数；不得用抽样点生成摘要。
- 关系：有效配对与缺失配对之和等于 eligible_count；确定性抽样可复现；二维所有箱计数之和等于有效配对数。
- 工具：新旧 schema、来源工具白名单、两维汇总、原子回滚、只改展示不查询、嵌套参数保留、复制作用域、选择映射、版本失效、撤销与清理。
- 渲染：六类图、分组与堆叠、评分顺序、分面、数量与比例格式、空数据、未知字段及不兼容类型；通过 Vega-Lite 编译并实际渲染代表样本，检查轴、图例和分布形状。
- 连续场景：执行上述两条链，每一步检查来源配置与显示结果；加入执行中修改和旧结果晚到的运行层测试。
- 泛化：现有教育适配器的图表与筛选测试继续通过；新渲染测试使用非电商字段，证明通用层不依赖 Olist 名称。
- 验证命令包括 .venv/Scripts/python.exe -m pytest、frontend 中 npm test 和 npm run build。真实 Olist 数据执行两条链的冒烟检查，记录样本量与响应时间，但不将本地计算时间称为实时语音延迟。

完成标准为上述工具可调用、六种图形可渲染、两条任务链及兼容测试通过，并交付测试结果和已知限制。仅写入接口 schema 或只生成图形规格不算实现完成。真实语音模型的工具选择成功率需另做在线验证，不由本地测试替代。
