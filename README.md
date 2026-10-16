# VerbalVis：可撤销响应事务与数据集接口化可视分析

这是独立于旧系统的新实现。保留原 Vue 仪表盘、图表卡片、对话时间线与麦克风外观；后端重新划分为八个核心模块。**本仓库仅限私有协作；尚未获准公开发布。任何公开仓库、公开 issue、release、tag 或归档均须先完成 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) 的全部门槛。**

## 项目做什么

用户通过持续语音对话提出分析问题，系统调用数据集自带的分析接口，执行真实 DuckDB 查询，并用通用图表工具创建、修改、筛选和高亮图表。用户改变问题时，后端撤销旧响应的后续执行与发布权限。工具即使不能物理取消，其私有草稿也不能覆盖新分析状态。

这里的泛化单位是 **数据文件 + 对应的 Python 接口文件**，不是承诺任何 CSV 上传后自动理解业务。接口负责数据语义、指标、SQL 和领域工具；运行时负责响应生命周期、事务提交和消息发送；前端按返回的字段元数据绘图。

产品界面、图表文本、系统语音/文字回答及参与者任务材料统一使用英文，供国际评审与演示使用。后续代理遵循 [AGENTS.md](AGENTS.md)；用户原始转写和原始数据值保持原样。英文任务材料版本为 1.1，已有排程和历史会话不回写。

作者直接阅读[六任务与旧 pilot 中文手册](docs/author/study-tasks.zh-CN.md)，其中保留八个中文提示词、探索思路、工具和预演说法。工作台以 16:9 电脑屏幕为设计基准：1920×1080 优先，1366×768 兼容；美学与分析正确性要求同样写入代理原则。

已有两个不同接口：

| 接口 | 数据 | 接口工具 | 典型口径 |
|---|---|---|---|
| Olist | 9 张实际 CSV，只读加载 | `aggregate` / `compare_segments` / `distribution` / `relationship` / `compare_periods` | 销售、评分、配送、商品物流与 seller 指标 |
| Education | 明确标注的合成教学数据 | `summarize_learning` | assessment 数、学生数、成绩均值、出勤率 |

两者使用不同字段、工具名和参数；没有在 `realtime.py` 或图表渲染器里增加“如果是教育/电商”的分支。Olist 保留 order、item、payment、customer 和 seller×order 粒度，查询默认只统计 delivered 订单；revenue 为 item price，不包括 freight。同一订单的多条 review 按 creation timestamp、review ID 降序选取唯一 canonical record。合成教育数据不代表真实用户研究。

## 启动

从仓库根目录使用 Python 3.11.14 和 Node.js 20.19+。除非命令以 `cd frontend` 开始，以下命令都从仓库根目录执行：

```powershell
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps -e .
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

打开 `http://127.0.0.1:8001`。默认使用教育接口。没有密钥时，HTTP、数据加载和界面仍可检查，但语音连接明确提示配置错误，**不会返回伪造模型结果**。

设置 `DASHSCOPE_API_KEY` 环境变量后重启后端。其他可选环境变量见 `.env.example`；应用不会自动加载或复制旧系统的 `.env`。模型与 API endpoint 必须属于相同服务区域。

选择 Olist：

```powershell
$env:VERBALVIS_CONFIG = 'configs/olist.json'
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

该配置默认读取被 Git 忽略的 `datasets/olist/data`，不会复制或分发数据。将九个 Olist CSV 放入该目录，或在本地（已忽略）配置中指定其他路径。配置文件里的接口、数据及 Trace 相对路径均相对仓库根目录；`VERBALVIS_CONFIG` 的相对路径也相对该根目录解析。

开发前端：执行 `cd frontend` 后运行 `npm run dev`，访问端口 5174，WebSocket 代理到 8001；结束后执行 `cd ..` 返回仓库根目录。

研究条件只使用规范名称：

- `/?condition=revision_enabled`：分析请求在旧请求尚未结束时仍可被接受；旧请求失去后续提交/发布权限。
- `/?condition=turn_taking`：上一个分析请求结束前拒绝新的分析请求；播放中的音频须收到匹配的自然结束 ACK 才算结束。

`full_duplex_rrt` → `revision_enabled`、`half_duplex` → `turn_taking` 仅作为外部 URL/配置 ingress 的兼容别名；进入 runtime 后 trace、session 和前端状态只使用规范名称。两条件共享相同的数据、工具、模型、提示词、dashboard、ASR 与 TTS。

同一进程只允许一个活跃实验会话。不要使用多个 Uvicorn worker；本实现不提供跨进程一致性。

## 八个核心文件

| 文件 | 唯一职责 |
|---|---|
| `backend/analytics.py` | 加载可信接口；校验 schema、结果版本、类型；串行化数据库访问 |
| `backend/dashboard.py` | 拥有公开状态；创建私有草稿；CAS 提交；管理 Undo 历史 |
| `backend/tools.py` | 合并领域工具与公共图表工具；参数检查；只修改草稿 |
| `backend/response_protocol.py` | 响应权限、intent epoch、批次去重、提交资格、一次性发送许可 |
| `backend/realtime.py` | 处理 Qwen 与浏览器事件；编排执行、打断、提交和后续生成 |
| `backend/prompts.py` | 从接口描述和已提交状态生成模型指令 |
| `backend/trace.py` | 有序研究事件；默认脱敏，不保存音频 |
| `backend/main.py` | 配置、FastAPI/WebSocket、单会话资源生命周期与静态前端 |

数据领域代码放在 `datasets/<name>/interface.py`，不是把 SQL 散落到运行时。

## Contract：接入第三个数据集

新增接口导出 `open_dataset(config)`，返回具备以下方法的对象：

```python
def describe(self):
    return {
        'dataset_id': 'your_dataset',
        'version': 'your-version',
        'description': '数据粒度、指标口径与局限',
        'filters': {'fields': ['region'], 'operators': ['eq', 'neq', 'is_null']},
    }

def tool_definitions(self):
    return [{
        'name': 'your_analysis_tool',
        'description': '工具做什么、返回哪些字段',
        'read_only': True,
        'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False},
    }]

def execute(self, name, arguments, scope=None):
    # 根据可信 schema 的白名单选择字段，值使用参数绑定；禁止模型拼接任意 SQL。
    return {
        'success': True, 'dataset_version': 'your-version',
        'rows': [{'region': 'East', 'amount': 42.0}],
        'columns': {'region': {'type': 'nominal'},
                    'amount': {'type': 'quantitative', 'label': 'Amount', 'unit': 'USD'}},
        'truncated': False,
    }

def close(self):
    # 关闭该接口自己创建的连接。
    pass
```

接口描述字段叫 `version`，查询结果和 dashboard 中叫 `dataset_version`，值必须一致。每一行的键必须与 `columns` 一致；缺失值用 `None`，禁止 NaN/Infinity 和嵌套表格单元。时间列为 ISO 日期/日期时间；Python date/datetime 会被规范化。类型支持 nominal、ordinal、quantitative、temporal。

共享 scope 为 `[{"field":"region","op":"eq","value":"East"}]`。接口必须解释并应用 scope；示例接口将共享 scope 和调用局部 filters 以 AND 合并。核心不替接口猜测业务含义。

失败返回 `success:false, dataset_version, error:{code,message}`；适配器还会将接口异常转换为这一格式。初始化/描述/schema 不合法则拒绝加载。接口是**可信本地 Python**，可读取文件和执行代码；这不是任意代码沙箱，接口路径不能由模型或浏览器提交。

公共工具：`describe_dataset`、`create_chart`、`update_chart`、`delete_chart`、`set_analysis_filters`、`highlight_chart`、`inspect_dashboard`、`undo_dashboard`。领域工具名不能与其冲突。

图表调用示例：

```json
{
  "source": {"tool": "summarize_learning", "arguments": {"group_by": "subject", "measure": "mean_score"}},
  "chart_type": "bar", "x": "subject", "y": "mean_score", "title": "学科平均成绩"
}
```

图表必须引用接口实际返回的字段；bar/line/scatter 有各自的类型约束。变更全局筛选时，重新执行每张图保存的 source；任一失败，不安装整个批次。

Olist 的核心查询不按问题名称拆成多个工具，而由一个语义词表驱动：

```json
{
  "group_by": ["order_week"],
  "metrics": ["order_count", "low_score_ratio", "avg_delivery_days", "late_ratio"],
  "filters": [{"field": "customer_state", "op": "eq", "value": "SP"}],
  "time_range": {"field": "order_date", "start": "2017-10-01", "end": "2018-04-01"},
  "sort": {"field": "order_week", "direction": "asc"},
  "limit": 100
}
```

`aggregate` 支持 0–2 个 group-by，固定 `metrics` 与动态 `measures` 合计 1–4 项，带 `having` 与固定成员 `top_k`。动态统计包括均值、中位数、连续分位数、阈值比例和已注册比值，须明确 order/item 粒度。`compare_segments` 支持参考组差值、相对差值、比例指标百分点差及批准的分类构成；`distribution` 返回完整数据直方图、箱线汇总或分位数；`relationship` 支持确定性抽样点、完整二维分箱及全数据 Pearson/Spearman 摘要。`compare_periods` 比较两个显式非重叠时期，支持汇总和对齐的日/周/月序列。值全部参数绑定；`between` 两端包含，`time_range` 使用 `[start, end)`。公开 Tool Schema 中不保留旧 `compare_commerce` 别名。原有指标公式见 `OLIST_ADAPTER_REPORT.md`；新增契约与限制见 [实验工具设计](docs/superpowers/specs/2026-10-16-study-tools-and-chart-layout-design.md)。

图表工具接受旧式 `chart_type/x/y`，也接受有类型的 `visual`（bar、line、scatter、heatmap、histogram、boxplot）。`update_chart` 的 `analysis_patch` / `visual_patch` 只修改列出的参数或白名单路径；`fork_chart` 默认固定当前有效范围，也可显式选择 linked。`set_selection` 使用来源图版本、实际标记谓词、目标图列表和 `highlight`/`filter`/`clear` 效果。无需语音服务的本地验收入口是 `python scripts/check_visual_analysis.py`，默认读取已有 `datasets/olist/data`。

## Visual Analytics Runtime

前端不认识 Olist 的字段名。图表类型、标题、单位、提示和数值格式均来自查询结果 `columns`；ratio 只在呈现层格式化为百分比，原始值仍为 0–1 数值。高亮只解释结构化 `{field,value}` / `{x_value,series_value}` 或在实际返回列中推断，不再内置电商字段别名。

`configs/olist.json` 可选配置 `initial_dashboard`。每项都是普通 `create_chart` 参数，不包含预计算 rows。会话初始化时，月订单、州评分、州订单、Top-15 品类收入和月配送时长依次走同一条 `create_chart → aggregate` 路径，全部成功后才一次提交为 revision 1。任意一图失败都丢弃私有 draft，并返回结构化 `initial_dashboard_error`。Education 未配置初始图，仍从 revision 0 空仪表盘开始。

这使初始图和对话中的创建、修改、筛选共用同一工具与数据口径；没有第二套前端预置数据或 Olist-only chart tool。实现合同与验收证据见 `M2_IMPLEMENTATION.md`、`M2_REPORT.md` 和 `PROGRESS.md`。

## Contract：响应、草稿与发布

1. 服务器创建响应权限，记录本地 response ID、intent epoch 和开始时的 dashboard revision。Qwen ID 只作映射，不授予权限。
2. 只在完整 `response.done` 后准入一次工具批次；重复 call ID、重复批次被拒绝。
3. 每个工具运行于 private draft。SQL 在线程中执行，不阻塞语音接收；接口连接由锁串行保护。
4. 所有调用成功后，同步执行“协议资格检查 → Store CAS 安装 → 协议记录提交”，中间没有 `await`。
5. 一个有实际状态变化的批次只增加一次 revision；只读或没有变化的批次不增加。失败批次整体回滚，先成功的调用也不得向模型谎报已提交。
6. 发送图表、工具结果与每条模型 function output 前再次检查当前权限；发送失败不能继续 follow-up。撤销不回滚已经合法提交的历史状态，Undo 是一个新提交。
7. 前端只接受带序号的消息与递增 revision；图表只由 `dashboard_commit` 更新，tool result 只更新动作卡片。

语音开始先暂挂，不直接推进 epoch。精确匹配的简短附和恢复旧响应；明确停止撤销；其他内容作为新分析意图。在线分类仅区分 `empty`、`backchannel`、`stop` 和 `analytical_request`；Goal、Hypothesis、Scope 是事后研究编码，不是在线控制标签。暂挂期间缓冲有界输出；空转写或 ASR 失败不等同于附和，应撤销未完成响应并提示重说。持续没有最终转写会明确报错，不无限等待。

## M3 研究生命周期与离线分析

每个 session 内的 analytical request 按接受顺序形成一条 request chain。一次 request 可以包含多个 provider response 和工具 follow-up；这些 response 不会被算作额外 request。只有在旧 request 仍处于 `reasoning`、`tool_execution`、`committing` 或 `speaking` 时接受的新分析请求才是 in-flight revision。`ResponseProtocol` 仍是唯一工具执行、dashboard commit 与输出发布权威。

工具批次把物理执行与公开 dashboard 状态分开记录：

| 情况 | `execution_status` | `commit_status` | `state_changed` | dashboard commit |
|---|---|---|---:|---:|
| 成功的只读批次 | `succeeded` | `read_only` | `false` | 否 |
| 成功但无状态变化的 mutating 批次 | `succeeded` | `no_change` | `false` | 否 |
| 成功且安装新状态 | `succeeded` | `committed` | `true` | 一次 |
| 工具调用失败并回滚 | `failed` | `failed` | `false` | 否 |
| 权限被撤销 | 实际执行结果 | `superseded` | `false` | 否 |
| 成功执行但 CAS 冲突 | `succeeded` | `conflicted` | `false` | 否 |

Trace v2 为每条记录保存 schema、session-local `seq`、UTC `observed_at`、纳秒 `monotonic_ns`、冻结的实验 context、correlation IDs 和结构化事件。默认会脱敏 transcript/arguments/payload，绝不保存原始音频；consent 不影响分析器的指标计算。离线分析使用标准库命令：

```powershell
python scripts/analyze_traces.py path/to/trace.jsonl
python scripts/analyze_traces.py path/to/trace.jsonl --output summary.json
python scripts/analyze_traces.py path/to/trace.jsonl --strict
```

分析器按 `session_id` 输出一个 trial-run；即使多个 session 有同一个 `trial_id`，也不合并 monotonic clock。它统计唯一接收请求、in-flight revision、Task 5 的 `batch.outcome` 中 superseded batches/calls，以及真实 `dashboard.committed` 批次。`duration_ms` 来自 session start/close；缺 close 时只是观测下界并标记 `duration_complete=false`。`time_to_final_state_ms` 仅使用最后一个接受请求的显式 request terminal event。`revision_saving_window_ms` 只有 trace 实际观测到对应 `previous_request_id` 的 settled timestamp 才计算；缺失、被 supersede、只有 `response.done` 时为 `null`，负差也只记录诊断并输出 `null`，不构造反事实等待时间。所有耗时输出为毫秒；输入 monotonic 时间戳为纳秒。坏行可恢复并报告 diagnostics；`--strict` 在仍输出结果后对数据质量问题返回非零。

分析器优先按唯一 `user.request_received.request_id` 计数；配对的 `request.received` / `revision.received` 不重复计数。若 trace 缺少部分 canonical receive event，会只用缺少的 request IDs 做 fallback，并发出 `request_count_fallback` 诊断。每个 revision 的 observed window 保存在 `revision_saving_windows_ms` 数组；便于比较的标量 `revision_saving_window_ms` 仅在该 session 恰有一条 in-flight revision 时有单一含义，revision 为零条或多条时为 null。分析器只访问用于统计的 ID、phase、canonical outcome 与 timing 字段，不读取或输出 transcript、arguments、audio、payload 或完整原始记录。通过自动化测试不构成 pilot/user-study 效果证据。

## 真实 Provider 的边界

本实现包含真实 Qwen WebSocket 传输，不在生产路径使用 Fake Provider。但还没有完成带凭证的真实语音联调。

为避免自动响应与手动 follow-up 混淆，连接要求服务端 `session.updated` 明确确认 `create_response=false` 和 `interrupt_response=false`。官方服务端示例包含这些状态字段，但客户端文档未保证每个模型都支持修改；不支持时本实现拒绝开始实验。**不能把自动化测试通过写成当前模型已验证兼容。** 参考 [Qwen client events](https://www.alibabacloud.com/help/en/model-studio/client-events) 和 [server events](https://www.alibabacloud.com/help/en/model-studio/server-events)。

协议保证本地接收/提交/发送许可边界；不能撤回已经发到远端的消息或已经被用户听到的音频，也不宣称可以事务性删除 Provider 内部历史。新响应会收到最新已提交 dashboard。更强的远端历史隔离需要供应商支持，或重建会话并回放受控历史。

## 验证与实验

### 六任务工具池与图表验收

新增任务池在 `experiments/olist_study_task_pool.json`，不替换下面的旧 pilot 排程。五个分析入口为 `aggregate`、`compare_segments`、`distribution`、`relationship`、`compare_periods`。接口与统计边界见 [实验工具设计](docs/superpowers/specs/2026-10-16-study-tools-and-chart-layout-design.md)；正式用户实验仍须完成真实语音预飞。

无模型密钥的确定性回放（不是模型或用户实验结果）：

```powershell
python scripts/check_study_tools.py --data-dir datasets/olist/data --export .superpowers/study-views.json
```

前端本地图表验收页使用生产 `ChartSlot`，不连接语音服务、不申请麦克风。先导出图表，再启动开发服务：

```powershell
cd frontend
$env:VERBALVIS_VISUAL_CHECK_MANIFEST = (Resolve-Path ../.superpowers/study-views.json).Path
npm run dev -- --host 127.0.0.1 --port 5175 --strictPort
```

打开 `http://127.0.0.1:5175/visual-check.html`。卡片按图形内容高度紧凑排列，界面不显示内部 view ID 或调试侧栏。类别热力图超过 24 类时按 20 类分页；横向条形图超过 20 类时按 14 类分页。分页保留完整数据及统一色域/数值尺度，查看全图时在卡片内滚动。添加 `?debug=1` 可查看用于长标题、缺失值和分面布局验收的 synthetic edge cases；它们不是 Olist 研究数据。

真实 pilot 不再依赖手写 URL：[Olist Pilot 运行手册](PILOT_RUNBOOK.md) 定义了预飞、四个交叉平衡序列、标准 trial 流程、失败/重试边界、每日 Trace 质检与 pilot 结束门槛；[正式实验冻结清单](STUDY_FREEZE_CHECKLIST.md) 明确了从 pilot 到正式 study wave 前必须固定的研究、软件、隐私和变更控制事项。任务与分配来自 `experiments/olist_pilot.json`，参与者排程使用：

```powershell
python scripts/prepare_pilot.py --manifest experiments/olist_pilot.json `
  --participant-id P001 --sequence-id S1 `
  --output pilot_sessions/P001.json
```

生成器只传递后端已验证的伪匿名 ID、task、dataset 和规范 condition；前端使用明确白名单把这些字段投影到 WebSocket URL，最终由后端再次校验并冻结到 Trace context。任务 prompt 不写入 URL，不作为隐藏模型提示词。排程保存 manifest version 和内容 SHA-256。`pilot_sessions/`、Trace、密钥和未经授权的参与者数据不得提交到 Git。

完成一批 trial 后，用排程与 Trace 做确定性对账：

```powershell
python scripts/audit_pilot.py --schedules pilot_sessions --traces traces `
  --output pilot_sessions/daily-audit.json --strict
```

审计器复用离线分析器的隐私安全投影，检查计划 trial 缺失、重复、context 错配、计划外 session、不完整 trace、无已接受请求和无最终状态；practice session 单独计数，不混入正式 trial。`--strict` 在存在任一诊断时返回非零。审计结果不包含 prompt、URL、transcript、tool arguments、audio 或原始事件。Goal / Scope / Hypothesis / Presentation 的事后人工标注规则见 [REVISION_CODEBOOK.md](REVISION_CODEBOOK.md)；这些语义标签不参与在线权限判断。

安装后从本目录运行（不依赖克隆目录名称）：

```powershell
python -m pytest tests -q
```

前端：

```powershell
cd frontend
npm test
npm run build
```

M3 离线 analyzer：

```powershell
python -m pytest tests/test_trace_analyzer.py -q
python scripts/analyze_traces.py tests/fixtures/trace_v2_analyzer.jsonl
```

Pilot 对账：

```powershell
python -m pytest tests/test_pilot_audit.py -q
python scripts/audit_pilot.py --schedules pilot_sessions --traces traces --strict
```

测试涵盖接口加载与 SQL 口径、不同领域图表、元数据投影、初始图原子物化、原子筛选、Undo/CAS、旧请求迟到、执行中修订、模型部分发送后撤销、半双工播放 ACK、附和恢复以及 WebSocket 资源关闭。测试中的 Provider double 仅代替外部传输，不代替应用的数据处理和提交链路。

`DATASET_REPORT.md`、`DASHBOARD_REPORT.md`、`M3_REPORT.md` 保存各子任务的测试证据；`PROGRESS.md` 保存整合进度。研究指标应来自真实任务与 Trace，不能由通过的测试数量推导成功率或用户收益。

实际 Olist 加载已验证 9 张原始表及 5 个 canonical grains：99,441 个 orders、112,650 个 items、103,886 个 payments；默认 delivered 口径为 96,478 单、BRL 13,221,498.11 revenue。Task A（SP，2017-10 至 2018-03，weekly 四指标）返回 27 周、15,495 单；Task B（RJ `office_furniture` vs `bed_bath_table`）返回 212 vs 1,357 单。详细口径和查询时间见 `OLIST_ADAPTER_REPORT.md`。这些检查验证数据与 SQL correctness，不代表 LLM 能力或用户研究效果。

尚需真人验收：指定模型的控制参数确认、连续语音/附和/意图修订、麦克风与扬声器回声影响、原界面视觉对照、真实非电商数据接口，以及全/半双工用户实验。实验室设备稳定不等于这些交互路径已经被验证。

默认 Trace 只保存 ID、决策、时序和结果状态，transcript/arguments/payload 脱敏且不保存原始音频。只有研究参与者同意后，才将配置 `trace_consent` 设为 true。当前没有可用 `DASHSCOPE_API_KEY` 的真实 Qwen 语音 pilot 证据；真实 provider、麦克风/扬声器交互与用户研究效果仍是外部验证边界，不能用自动化测试代替。不要发布 Trace、密钥或未经授权的数据。
