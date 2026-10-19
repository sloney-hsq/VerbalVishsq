# VerbalVis 十二人语音组间实验设计

日期：2026 年 10 月 19 日。状态：按用户确认的简化范围修订，研究执行细则与工程实施待审阅。本文替代此前的语音与文字对照方案；不代表相关功能已经实现。

## 1 研究问题与结论边界

12 位参与者，每人只完成一个正式任务、体验一种语音条件。全双工组和 turn-based 组各 6 人，共 12 个计划 trial；不采用交叉顺序、不做参与者内配对，也不是 24 或 48 个 trial。

- RQ1：固定探索时间下，两种语音交互策略的最终分析论证质量呈现什么差异？
- RQ2：两组如何在连续分析请求中修订范围、问题和解释？全双工组何时使用执行中修订，何时造成干扰？
- RQ3：参与者如何描述等待、讨论连续感和控制感？图表如何成为下一步提问的依据？

定位为资源约束下的小样本探索性组间对照。不能预先声称样本量足以证明优越性或等效性；不显著不等于相同。两组都有语音和动态图表，因此不能单独估计语音模态、拟人感或图表的因果效应。[样本量论证依据](https://lakens.github.io/statistical_inferences/08-samplesizejustification)

## 2 条件与控制变量

| 条件 | 规范标识 | 行为 |
| --- | --- | --- |
| 全双工语音 | revision_enabled | 系统仍在推理、查询或讲解时可说话；附和恢复旧响应，新分析请求撤销旧响应后续权限 |
| Turn-based 语音 | turn_taking | 当前完整分析请求结束前不接受下一分析输入；包含工具 follow-up 和最后语音的匹配自然播放结束 ACK |

两组使用同一模型、声音、ASR、工具、提示词、数据、初始面板、设备和界面。唯一操纵是既有 revision policy；不人为增加延迟。产品与参与者材料英文，作者说明中文。用户原始表达不翻译覆盖。

Turn-based 忙碌时不上传分析音频；不录制其被阻止的语音来推断需求。两组均保留明确 Stop 控制，用于主动终止当前回应；Stop 不自动发起新分析，记录使用次数。只暂停麦克风采集不能被误记为停止分析。

正式入口由服务端 assignment 决定 condition；URL 和消息不能覆盖。正式分析阶段拒绝浏览器 typed-text 输入，内部 ASR 仍进入共享 accept_text 路径。保留旧非 study 入口，不重写 ResponseProtocol。

## 3 任务与分配

沿用用户确认的任务池 2.0，两题均为有初始假设的开放探索，不是自由生成问题任务。题目不要求参与者打断、改阈值或按固定工具顺序操作。

| 任务 | 数据范围与问题 | 全双工 | Turn-based |
| --- | --- | ---: | ---: |
| A：review-delivery-association | 2017 年购买、送往 SP/RJ 的 delivered 订单；配送时长与 1–5 分评价是否有关，何处需要限定 | 3 | 3 |
| B：freight-attribute-association | 同期同地区 delivered 商品项，price > 0；重量与 freight/(price+freight) 是否有关，是否支持优先调查重商品 | 3 | 3 |
| 合计 | 每人只做其中一题 | 6 | 6 |

保留两个任务是为了覆盖两类分析内容；不宣称二者难度相等，分析时保留 task 分层。任务平衡用于降低任务与条件混淆，不保证所有个体差异平衡。[区组设计依据](https://www.itl.nist.gov/div898/handbook/pri/section3/pri332.htm)

排程在招募前生成：将 12 个伪匿名 ID 按固定 seed 打乱，前 6 人分配 A、后 6 人分配 B；在每题 6 人内随机分配 3 人到每条件。保存 seed、算法版本、manifest 哈希与实际分配，禁止按表现换组；不要直接按招募顺序轮流分组。分析经验只作基线描述，不在 12 人中再拟合多项协变量或任务×条件交互。

新 manifest 规划为 experiments/olist_voice_policy_between_v1.json。复制现有任务池的两份英文 title/prompt，记录源文件字节哈希与各 prompt UTF-8 哈希；不恢复旧六题清单。旧六条工具回放仍可作为技术验收，不是正式实验六题。

## 4 单人流程

默认时限沿用原提案，正式采集前经预飞固定：

1. 同意与背景资料约 3 分钟：分析经验、图表熟悉度、语音工具经验；身份映射单独保存。
2. 在分配的唯一条件下练习约 3 分钟，使用无关练习题。只说明该条件的交互规则，不要求制造打断；不体验另一条件。
3. 关闭练习 session，创建全新正式 provider/dashboard/Trace；provider 和初始图渲染确认后才允许 Start。
4. Start 后显示英文任务，探索 600 秒。题目不作为隐藏模型提示词注入。默认固定时限，不以“做到某结论”为结束标准。
5. 截止冻结最后合法面板；渲染与证据持久化均确认后，提供 180 秒填写 conclusion、evidence_refs、limitations。两组均使用相同文字答题表单，这不是分析条件。
6. 完成简短问卷约 2 分钟；授权情况下回顾访谈约 5 分钟，询问具体改问、等待及看图片段，允许负面体验。

每人约 26 分钟，加上设备和冻结等待缓冲。常规不提前结束探索；参与者可停止提问、观察或主动退出。第一版不提供 trial.finish 提前冻结入口；异常退出按中止处理，记录实际时长，不混作完整 600 秒数据。

## 5 结果变量与人工评估

### 5.1 唯一主要指标

最终论证质量总分 0–9；评分草案在正式采集前用非正式样例校准并冻结。两名评分者先独立评分全部有效答案，保留原分，再讨论裁决；主要分数使用两名独立总分的平均值。

| 维度 | 0 分 | 1 分 | 2 分 | 3 分 |
| --- | --- | --- | --- | --- |
| 结论与口径正确性 | 无结论或核心结论错误 | 有明显粒度、变量或范围错误 | 基本正确但适用范围不完整 | 结论与任务口径一致，明确支持、反对或证据不足 |
| 图表证据支撑 | 没有相关证据 | 提到图表但不足以支撑结论 | 有可定位证据但解释欠充分 | 引用有效图表版本，解释关系、数量/分布及必要限定 |
| 限制与替代解释 | 无限制或声称因果已证实 | 只有泛泛提醒 | 提出与本分析有关的限制 | 解释该限制如何影响结论或决策 |

A 校准关注 order 粒度、评分去重、配送时长不等于逾期；B 关注 item 粒度、正价格、比例分母与价格混杂。不得给特定结论、图表数量、修改数量或用了某工具自动加分。真实数据 oracle 需在预飞时查询，本文不预写相关方向。

评分包只含匿名答案、任务与冻结的证据附件，不含 condition、对话或延迟日志；人工检查回答是否自行透露条件，不承诺绝对盲化。

### 5.2 次要和过程指标

- 问卷为自编单题 1–7 分：思考/表达连续感、控制感、主观努力、等待干扰；各题分别报告，不包装成已验证量表或随意合成总分。
- 全会话修订：在每位参与者已接受的连续分析请求间，人工判断是否修改问题、范围、假设或呈现；初始请求、普通新问题和有意义修订分开。
- in-flight revision 只作机制使用描述。Turn-based 不能接受此类输入，不能据其为零推断该组不想修改或思维不活跃。
- 记录误听纠正、工具/渲染失败、Stop、请求与提交/渲染关联；总请求量、图表量不等于分析质量。
- 图表反馈的作用结合授权转写、已确认渲染版本和回顾访谈判断。“图表完成后发生提问”只表示时序关系，不自动编码为图表导致提问。
- 原 REVISION_CODEBOOK 只覆盖 in-flight，作为历史材料保留；新全会话规则与输出字段写在本研究材料中，不能直接沿用其排除所有 settled 后请求的规则。未授权转写标为 not_codable，不从工具参数反推语义。

问卷文案草案统一使用 1=Strongly disagree、7=Strongly agree，不询问没有体验过的另一条件；正式收集前固定：

| 字段 | 英文题项 |
| --- | --- |
| continuity | I could maintain my train of thought while using the system. |
| control | I felt in control of the analysis. |
| effort | Expressing my analysis requests required substantial effort. |
| waiting_interference | Waiting for the system disrupted my analysis. |

后两项高分表示负担较高，不与前两项不经说明相加。

### 5.3 分析单位和统计方案

独立单位为参与者，最多 n=12；同一人的多个 request、图表或修订片段不增加独立样本量。不用配对 t 检验、交叉设计或 24/48 行作分母。

先画全部个体分数，按 task 标记，报告各组及各题的描述统计。主要效应描述量为两任务等权的“全双工均分减 turn-based 均分”；完整平衡数据时等于两组总体均分之差。

可预先指定 task 内受限随机化检验作探索性补充：每题保持 3/3 标签，完整数据共有 C(6,3)^2=400 种分配；统计量使用上述等权差，双侧包含与观测同样极端的分配。它检验随机分配下的尖锐零假设，不提供功效保证；不在看到数据后挑检验。存在缺失/排除时不能直接套用完整 400 分配检验，先报告缺失及其与条件的关系，定量对比以描述为主。次要指标不批量寻找显著性。

两题每个条件仅 3 人，不作任务×条件交互效应结论。论文结论以观察到的过程、表现与局限为准，不把探索性结果写成“全双工普遍促进思考”。

## 6 失败和研究有效性

12 人对应 12 个计划 assignment，技术失败不能增加独立 n。正式题目尚未展示的连接故障可在同一 assignment 下新建 attempt；旧 attempt 保留并中止。题目展示后的失败不得自动重做并把第二次当首次表现；记录暴露与原因，本研究不自动补人或重收，任何变更由研究团队另行决定。

低分、无修订、不支持预设假设不构成排除理由。技术完整但答案留空，保留 empty 状态并按评分规则计零；退出、写入失败或没有可评分数据属于缺失，不能伪造为零。有效样本可能少于 12，按实际数量报告。

知情同意、伦理、退出/保留规则和评分细则须由研究团队批准。自然插话很少不是软件技术失败，也不应诱导参与者制造事件；应如实降低机制使用方面的主张。

## 7 工程范围

P0 仅交付完成本次研究所需的闭环：

- 保持已有两种语音策略，补足完整 request、播放结束和截止竞态验证。
- 新建 12 人组间 manifest、受控 assignment、单正式 trial 面板。
- 服务端计时、截止冻结、真实图表渲染确认。
- 保存合法提交的证据、最终答案、简短问卷；输出匿名盲评包和技术审计。
- 保留 Trace v2，新增独立版本化 study journal，通过 session_id 关联，不全面迁移 Trace v3。

不新增文字分析模式、interaction_mode、模式切换、交叉排程、在线意图分类、新数据集或分析工具。保留已有 tooltip、分页、图表工具与模型调用路径。新增鼠标筛选/基线/Undo 按钮、选择指代服务、复杂联动与可编辑修订树列为后续工作，不作为这 12 次实验的前置条件。现有模型工具仍可完成筛选、复制和撤销。

## 8 生命周期和记录边界

StudyController 管理 preparing → ready → exploring → answering → completed；任一未终态可 aborted，终态不能反转。StudyStore 使用受控目录内 SQLite 存 assignment/attempt/session 映射、journal、幂等回执、答案和证据索引，不持有 Dashboard 权限。

Start 以服务端 monotonic 时间为准。exploring 的 600 秒边界在音频准入、ASR 接受、工具 commit 和实际输出发送处同步检查，不能只依赖异步 timer。截止先关闭分析准入、撤销未完成 response，捕获最后合法 snapshot；不能撤销已经合法提交的图。

上述 gate 针对参与者分析 effect；provider 配置、已有构造阶段的初始面板物化、init、研究状态、渲染及错误控制消息有明确独立的启动/控制路径，否则 preparing 会因无法发送初始图而死锁。例外不能接受任意分析工具或让模型请求绕过 gate。

初始、每次 commit 和冻结均登记 render_token、dashboard_revision、预期 view revisions。ChartSlot 在 Vega embed/runAsync 完成且 generation 仍有效时 ACK；Dashboard 汇总当前 token，旧 ACK/未来版本/未挂载 view 不算完成。空面板显式完成。分页 ACK 只证明当前页，nextTick/投影成功不是实际渲染证明。第一版可对每个新 token 全部重新渲染，暂不做跨 token 完成证明复用。

冻结必须新发完整 snapshot 与独立 token，即使最后一次 commit 尚未发送也能显示。记录 frozen_committed_revision 和当时 last_rendered_revision。冻结渲染与必需证据共同最多等待 15 秒，分别失败为 frozen_render_failed/evidence_persist_failed；确认两者完成后才开始 180 秒答题计时，等待不混入探索时长。不在冻结后查询来重建历史。

证据在初始合法面板及每次合法 commit 后捕获不可变 views/data/columns/metadata/visual/source 白名单、dataset_version 和 renderer 代码版本，由独立持久化队列保存并登记哈希。只保存返回的有限图表数据，不复制数据库。commit 原子边界内没有 await 或文件 I/O；响应撤销不删除以前合法证据。每 attempt 最大 50 MiB，超限/写入失败 fail-closed，不静默截断。只有 evidence_ready 的同 attempt 版本才能被答案引用。

答案总文本不超过 8000 字符；submission_id 与 client_event_id 分别做业务和消息幂等，同 ID 同内容返回原回执，不同内容冲突。answer.save 按单调 draft_version 保存已确认草稿；180 秒到期保存最近确认草稿为 partial/empty，不伪造主动提交。问卷缺失不改变答案完成状态。刷新/断线/进程重启使未终止 attempt aborted；completed 后断线不能抹掉已存答案。

## 9 同意和导出

同意分 transcript、analysis_evidence、final_answer；正式研究要求后两者，transcript 可选。Trace v2 既有脱敏保持；journal 仅白名单事件元数据，选择值、自由文本错误不得绕过同意。答案和图表 artifact 按各自授权保存，不塞进普通 trace。原始音频不保存。

研究目录、排程目录与导出目录均受可信配置约束并 Git 忽略；客户端只引用 assignment_id，不提交路径、condition、participant 或 snapshot 作为权威。记录 commit/dirty、模型/提示词/工具 schema、数据与初始面板哈希，正式收集禁止未知脏版本。

audit_study 按计划 assignment 对账 12 人/12 trial/四个 3 人单元格，attempt 和 practice 单独列示。export_study 分离技术质检、盲评答案、授权过程编码三个包；脱敏包无 mode/condition 信息，过程包不得冒充盲评。两个包都不整段复制原始日志。只使用同一时钟域计算时间差。

## 10 分工与验收

沿用多个 GPT-5.6-Sol（medium）的执行选择，批准实施计划后按文件所有权并行：

| Owner | 独占范围 | 输出 |
| --- | --- | --- |
| A 运行时整合 | main.py、realtime.py、研究生命周期 study.py 及相应集成测试 | 条件锁定、截止 gate、冻结与 study 接线 |
| B 前端与渲染 | frontend/src、frontend/tests；新 render_tracker.py 及专项测试 | StudyPanel、渲染 ACK、答题与问卷 |
| C 研究数据 | study_store.py、study_manifest.py、study 脚本、manifest 与数据测试 | 平衡排程、持久化、审计和安全导出 |
| 主代理 | 设计/计划、README/作者说明、审查与整体验收 | 统一接口、回归结果及预飞边界 |

先冻结共享消息与 Store/Tracker 接口，然后 B/C 可并行；A 的集成依赖接口交付。不得多个代理同时写 main.py、realtime.py 或 useWebSocket.js，不自动合并或推送。

必须覆盖：12 个唯一 assignment/每人一题/每条件六人/每 task×condition 三人；条件伪造；turn-taking 完整 follow-up+音频 ACK；截止前执行但截止后 commit；旧 render ACK；15 秒冻结失败；幂等冲突；50 MiB 边界；三类同意；重启和 completed 后断线；旧 pilot/Trace v2 回归。两任务两条件真实 provider 预飞、实际桌面图表检查和正式用户研究分别报告，不能用测试数量替代。

[工程实施计划](../plans/2026-10-19-voice-policy-between-study.md)
