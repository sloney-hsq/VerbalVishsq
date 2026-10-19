# VerbalVis 语音与文字对照研究重构设计

日期：2026 年 10 月 19 日。状态：待用户审阅。适用读者：项目作者、实现代理与验收人员。

本次改造保留现有分析引擎，建立可比较的语音与文字讨论入口、共享图表交互、独立任务生命周期，以及可供人工评价的研究记录。目标是支持 12 人的被试内探索性研究，而不是证明语音、亲切感、图表和全双工各自独立的因果作用。

用户已确认对话中的工程范围并要求子代理参与。本文批准后进入实施计划；实施计划审阅后按已选择的子代理方式执行。本文不是完成报告，不代表新增接口已经存在。

## 1 研究目标与范围

核心问题是：在动态可视分析环境中，语音讨论怎样影响问题的逐步明确、探索性修订与最终证据质量？通过过程记录观察图表如何参与后续提问，但本研究没有无图表条件，不能据此估计图表的独立效应或模态协同效应。亲切感、连续感和负荷只作为体验与机制线索。

12 名参与者都经历两种方式，每种方式完成两个不同任务。两组共享数据、分析工具、图表交互、上下文、修订策略和提示词；差异是语音输入输出与文字输入输出。主要结果为固定探索时间后的最终论证质量，修订模式和负荷是探索性结果。48 次任务记录不是 48 名独立参与者。

产品、助手回答和参与者材料保持英文，作者说明保持中文。保留用户原始转写。参加者知情同意、纳入标准、评分与数据保留规则由研究团队在收集前批准，软件不能自动勾选。

### 1.1 范围内

- 真正的纯文字模式与现有语音模式，统一的分析执行路径。
- 单标记选择、明确筛选、固定基线和撤销，以及两种讨论方式共享的指代上下文。
- 指标、粒度、范围、样本量和警告可见；真实渲染成功与失败记录。
- 独立 trial、服务端计时和冻结、最终答案、简短问卷、排程、对账与人工编码导出。
- 保留旧 revision policy 实验与 Trace v2 读取兼容。

### 1.2 范围外

不扩充五类分析工具，不新增数据集、在线 G/S/H 分类器、拟人化声音对照、无图表对照、复杂修订树编辑器、自动因果判断或任意 CSV 理解。不重写 ResponseProtocol，不合并主分支或推送 GitHub。

## 2 基线与方案选择

实施基线为附加 worktree `C:/Users/admin/.codex/worktrees/visual-analysis-tools/VerbalVis`，审阅时 HEAD 为 `ffa7673`。其 `experiments/olist_study_task_pool.json` 有已有未提交修改，不能覆盖或带入文档提交。主目录 `C:/VerbalVis` 的研究文档仍以 in-flight revision 对照为主，且存在未提交材料；不得直接覆盖。

| 当前位置 | 已有基础 | 改造缺口 |
| --- | --- | --- |
| backend/realtime.py | accept_text、音频转写、请求与事务编排 | configure 固定 text/audio；缺少独立模态及输入来源 |
| backend/main.py | text/audio WebSocket 入口、ACK 校验 | 缺少服务端排程约束、trial 与直接操作入口 |
| backend/conditions.py、trace.py | 旧条件及不可变研究上下文 | condition 不能重解释成语音/文字 |
| frontend/src/composables/useWebSocket.js | 音频与提交消息、投影 ACK | 未暴露 sendText；缺少统一研究事件发送 |
| ChartSlot.vue | Vega 嵌入、tooltip、布局与分页 | 缺少语义选择事件和实际渲染完成汇总 |
| backend/tools.py、selection.py | 五类分析、选择、复制和撤销工具 | 直接操作尚未与会话权限连接 |
| scripts/prepare_pilot.py | 两任务、四序列及安全校验 | 硬编码旧 pilot 设计，不能直接使用新排程 |

采用增量改造。只加输入框并静音的方案不能消除隐藏音频生成及播放等待；完全重写运行时会扩大回归范围。新研究模块管理 trial，不获得独立提交权限。

## 3 条件与配置契约

保留 `condition = revision_enabled | turn_taking` 的全部含义；新增 `interaction_mode = voice | text`。本研究的两个模式都固定 `condition=revision_enabled`。旧入口未提供新研究标识时保持原语音默认行为；新正式研究缺字段时拒绝启动，不能悄悄使用默认模式。

正式上下文增加 `study_id`、`study_version`、`manifest_sha256`、`assignment_id`、`attempt_id`、`interaction_mode`，并保留 participant/trial/task/dataset/session ID。服务端从本地受控排程解析，浏览器只传 assignment 引用，不能提交模式作为权威。禁止模型调用研究控制接口。

研究目录、排程加载位置由可信本地配置指定；浏览器不能提供任意文件路径。单进程单活跃会话限制不变。正式任务期间无模式切换按钮。记录代码提交、脏工作区标记、模型、提示词和工具 schema 哈希、数据版本、初始面板配置哈希及非敏感 provider 参数；正式冻结禁止未知脏版本。

### 3.1 provider 与输入生命周期

- voice：音频输入、语音输出和可见转写；沿用 ASR 重叠控制与自然播放结束 ACK。
- text：input_text 消息、纯文字输出；不创建麦克风捕获，不生成音频，不等待播放 ACK。无工具 follow-up 的最终文字 response 完成后才 settle；工具 response.done 不是整个 request 的结束。
- 保持同一模型、工具与语言策略。不支持纯文字与工具调用的 provider 必须报 configuration_error，不采用静音伪装或偷偷换另一模型。
- provider 握手按模式分别验证：voice 要求确认手动响应与重叠控制；text 要求确认纯文字输出和由本地 response.create 驱动，不能继续强制其返回语音 VAD 配置。确认契约不完整时不发送 session_ready；text 模式收到意外音频或语音自动响应时记录契约错误并停止 trial，不能静默丢弃后声称模式正确。
- 两模式均核对工具配置，并保持 pending generation ticket 与 response.created 的绑定要求；未经本地票据的 provider 响应不能获得权限。握手字段以实际 provider 预飞确认的协议冻结，不通过放松权限校验兼容未知响应。
- 同一模式内使用统一简短解释策略，不给语音组额外引导性追问。ASR、输出模态是实验包的一部分，研究不宣称隔离了亲切感或单独的输入速度作用。
- accept_text 显式接收 source=text/voice_asr、client_event_id 和已冻结的上下文；ASR item_id 仍承担转写去重，不与浏览器 event_id 混用。
- input_policy 增加 accepts_text、accepts_audio、trial_phase、interaction_mode。前后端共同限制，后端是权威。
- 去重键为 attempt_id 与 client_event_id；相同 ID、相同载荷返回原结果，相同 ID、不同载荷返回 conflict。重复消息不能执行两次。开发模式限制去重缓存并拒绝过期未知序号，正式模式按有限 trial 保留登记。
- typed text 最长 4096 字符；事件不接受任意嵌套 payload。空输入、停止与附和沿用共享规则。文字组需要 Input Method Editor composition 防误发送。

首个技术门槛是同一真实 provider 的两模式预飞。不支持时停止正式研究上线；模拟 provider 只用于测试。

## 4 前端讨论与分析工作区

新增 `ConversationComposer.vue`，文字组显示输入框与 Send，语音组显示录音入口；均显示 Stop、状态和对话记录。发送失败保留文字草稿，接受后显示服务器关联的 request，不将乐观 UI 标为工具成功。两组的图表面积、历史、按钮与错误提示一致。

延续 1920×1080 优先、1366×768 兼容的工作台。保持稳定卡片位置，不因最新请求自动重排；密集 heatmap 跨列。保留类别顺序、数据范围、缺失显示和全局色标；分页只是呈现，不产生分析修订。

每图显示工具元数据派生的指标与单位、统计方式、粒度、时间范围和固定基线标记；样本量、抽样、覆盖或抑制警告可展开。未知元数据标示未提供，不由模型编造。

### 4.1 选择与指代

第一版交付单标记选择：bar 类别、line 时间标记、histogram 区间、boxplot 分组、scatter 点或分箱、heatmap 单元格。用户可以点击并查看选择摘要、Clear selection、Filter targets、Keep baseline 和 Undo。复杂多选集合、任意套索及跨图不规则 OR 谓词不在本轮。

Hover 为本地瞬时查看，不撤销请求。点击产生本地候选并向服务端申请 selection；只有确认后的 selection_id 可以供后续分析引用。选择单个 heatmap 单元格保留行列及系列键；分箱记录明确上下界及包含关系。选中聚合值可高亮，但不能把均值、相关系数等派生列当作原始字段筛选。只有现有 selection_filters 能安全映射的谓词开放 Filter targets，否则显示不能筛选的原因。

服务端选择上下文包含 selection_id、focused_view_id、source_view_revision、dashboard_revision、context_revision 和白名单谓词。context_revision 是指代上下文版本，不是第二份 dashboard 权威。图表变化只在相关来源失效时清除选择并告知用户；不得默默将旧 selection 绑定新数据。

文字发送显式引用已确认 context_revision。语音在服务端处理 speech_started 时固定当时已确认的上下文，最终 ASR 沿用该版本，不改用转写结束时的新焦点；记录这一捕获边界，不能当作精确声学起点。若上下文缺失、过期或指代不唯一，简短澄清，不猜测更改全部面板。

### 4.2 直接分析操作的权威

选择/焦点本身不构成新分析请求；Filter targets、Keep baseline、Undo 属于明确修改。新增窄的 action dispatcher，将它们映射到已有注册工具。UI 不得提交任意工具名、SQL 或 dashboard snapshot。

直接修改创建 source=pointer 的本地分析请求，经过同一 ResponseProtocol 撤销/准入、private draft、CAS 和 dashboard_commit；可提取公共执行方法，但不能在 main.py 直接 commit。直接操作默认不触发额外模型解释，两种模式一致；下一次对话获得新的已提交快照。正在执行的模型请求被明确修改替代时，通知用户并保留以前合法提交。

## 5 任务生命周期与持久化

新增 `backend/study.py` 管理状态与规则，`backend/study_store.py` 使用标准库 SQLite 存储有限研究状态、事件去重登记和答案引用。数据库位于受控 study_data 目录并被 Git 忽略。短事务提交成功后才确认成功；写入失败使 trial fail-closed。StudyStore 不写 Dashboard，也不授予响应权限。

| 阶段 | 进入条件 | 允许行为 |
| --- | --- | --- |
| preparing | assignment 验证、全新 provider/dashboard session | 初始图渲染、连接验证；不接受分析 |
| ready | provider 就绪、初始面板渲染确认、同意配置匹配 | Start task |
| exploring | 服务端接受 Start，展示英文任务 | 分析、图表操作与观察 |
| answering | 到截止或 Finish exploration 后冻结 | 查看冻结证据、填写最终答案；不再查询 |
| completed | 最终答案已持久化 | 提交固定问卷；结束会话 |
| aborted | 断线、服务异常、关键记录失败或退出 | 保存诊断；不得恢复成原 trial |

初始面板对同一任务在两种模式下完全一致，来源与哈希固定。正式计时前不显示任务具体题目；Start 的服务器时间为主要开始边界，另记题目实际显示 ACK。任务文本不自动注入模型。

设计默认 exploration_limit_seconds=600，answer_limit_seconds=180；值写入 manifest，研究团队可在首名正式参与者之前修改并升版本。问卷位于独立后续阶段，问卷缺失不改写答案完成状态。

### 5.1 截止与冻结

服务端 monotonic deadline 是权威；浏览器倒计时仅展示。接收新输入、工具批次提交和实际输出派发都检查 trial 是否有效，不能仅依赖计时器回调。检查不得在 commit 的同步原子边界中引入 await。

到期时同步关闭研究准入并通过现有 protocol 撤销未完成响应的后续权限，记录当前最后一个合法 committed snapshot 及 revision。随后停止音频、发出 trial.frozen 与该快照；之前合法提交不会回滚。已发出的音频不可追回。

记录 frozen_committed_revision 与截止时已知的 last_rendered_revision，不把尚未显示的提交当作已看到。冻结面板允许完成同一版本的渲染，但不得重新查询；冻结渲染最多等待 15 秒，失败则中止为 frozen_render_failed。答案阶段计时从该冻结版本渲染与第 8 节必需证据持久化均确认后开始，并记录等待时间，不计作探索时间。

trial.frozen 必须为冻结 snapshot 登记独立 frozen_render_token 和预期 view revision 集合，并携带完整冻结面板。公开状态可能已合法 commit、但尚未经过网络发送，因此不能假设旧 dashboard_commit token 已在浏览器存在。上述 15 秒等待和答题启动只接受这个 frozen_render_token 的完成证明，旧 ACK 不得触发答题。

探索结束后的答案最长 8000 字符，结构为 conclusion、evidence_refs、limitations。服务端限制引用为该 attempt 已存在的不可变 snapshot/view revision。相同 submission_id 重发幂等；不同内容冲突不覆盖原答案。答案截止时保存最近一次已确认草稿并以 answer_status=partial/empty 结束为 completed，不虚构 answer.submitted 事件；主动提交为 answer_status=submitted。completed 只表示采集流程终止，不意味着回答完整或研究上有效。只有完成持久化才能显示 Saved。

刷新、浏览器断线或进程重启不续接旧正式任务；持久化 journal 将未终止 attempt 标为 aborted，使用新 attempt 重试，并保留原记录。已持久化的 completed 答案不会因随后断线变为 aborted。研究文件写入路径不由客户端指定。

## 6 消息边界

新消息采用有类型白名单，全部带 client_event_id；身份从当前 socket 的服务端 assignment 解析，禁止消息覆盖 participant、mode 或 attempt。

| 浏览器消息 | 主要字段 | 服务端结果 |
| --- | --- | --- |
| text | text、context_revision | input.accepted/rejected，与现有 transcript/request 关联 |
| context.set | view_id、view_revision、mark_predicate | context.confirmed 或 stale/invalid，不改图表数据 |
| chart.action | action、selection_id、target_view_ids、base_revision | action.accepted/rejected，成功通过 dashboard_commit 更新 |
| trial.start | 无任务覆盖字段 | trial.state，含 server deadline |
| trial.finish | 无客户端自报完成时间 | trial.frozen 与固定 snapshot |
| answer.save | 草稿版本、答案字段 | answer.saved，返回版本 |
| answer.submit | submission_id、答案字段 | answer.submitted 或冲突 |
| questionnaire.submit | 白名单题项及合法分值 | questionnaire.saved |
| view.rendered / view.render_failed | render_token、view_revision、render_generation | 记录与批次聚合；不能改变 trial 模式 |

另有 Stop 控制消息，在两模式均可使用；不走文字组限制旁路。trial 关闭期间 Stop 仍可停止本地播放，但不能恢复分析准入。音频 PCM 格式保持现有协议，不逐帧写研究语义日志。

## 7 渲染测量

每次 init/dashboard_commit 由服务端登记 render_token、dashboard_revision、关联 request/batch 及预期 view revision 集合。ChartSlot 在 Vega embed/run 完成且本代仍有效时发出组件级完成事件；失败明确上报。Dashboard 汇总同一 token，旧代、旧版本、重复 ACK 不计入新版本。

从上一版本保留下来且内容、布局未变的已完成视图可复用已有完成证明；新建或变化视图必须完成当前代渲染。删除图从预期集合移除；空面板按显式空集合完成，不等待不存在的 ChartSlot。隐藏或未挂载视图不能伪装为已渲染。分页只证明当前呈现页完成，不证明全部类别被看到。

服务端校验 token、实际预期集合及当前 attempt，拒绝未来版本与伪造 view。浏览器上报始终是客户端观测，不等于物理屏幕呈现或用户注意。浏览器耗时只在浏览器时钟内计算，服务端接收耗时只在服务端时钟内计算。

## 8 Trace 和证据导出

新增 Trace v3 用于新 study；旧 v2 文件保持原样。解析器显式分版本，缺失模态的 v2 不能自动算入语音/文字正式对照。继续保留现有 seq、ID、phase、commit 与 outcome 验证。

新增事件包括 input.received/accepted/rejected、context.confirmed/invalidated、chart.action、view.rendered/failed、trial.started/frozen/aborted、answer.saved/submitted 与 questionnaire.saved。事件通过来源标记区分服务器事实、客户端报告和人工编码。

分析链复用现有 root/parent/request 标识，并加入 source、捕获的上下文版本、before/after revision、变化的 view 和白名单参数路径。不把每个请求都标为“有意义的修订”，不从工具名推断 G/S/H。

### 8.1 隐私分层

- Trace 默认只存身份代号、版本、计时、状态、计数和受限元数据；无原始音频。
- 同意范围分为 transcript、analysis_evidence、final_answer；正式研究要求 analysis_evidence 与 final_answer，transcript 可选。transcript 只授权原始对话转写；analysis_evidence 授权返回图表数据、白名单分析参数和选区值；final_answer 授权参与者提交的结论、依据与局限。不以某一项授权替代另一项。
- 渲染证据采用受控 artifact：实际返回的有限图表数据、语义与 source、图表规格、数据版本及内容哈希，不复制整个数据库。artifact 与研究数据库在同一受控根目录，拒绝路径穿越。
- 未授权类别不得通过 selection 值、自由文本错误、参数 diff 或答案字段绕过脱敏。analysis_evidence 的 source 仅保留白名单工具参数，不附加原始 prompt 或对话。transcript=false 时仍可保存已授权的答案和图表证据，但依赖对话的过程编码标为 not_codable；不能从参数反推用户语义。保留既有 Trace sanitizer，并显式新增分类型存储许可，不能换字段名绕过。
- 每 trial 证据 artifact 总量上限 50 MiB，达到上限不得静默截断后声称可重建；中止并记录 evidence_limit。此上限在正式预飞前验证足够覆盖任务，改变需升 manifest 版本。
- 不自动开启屏幕录制；研究团队另行批准的录屏可作为回顾材料并分开保存身份映射。

每次合法 commit 捕获对应的不可变结果、规格与 source，先在内存关联版本，再由 study 所有的持久化队列写入 artifact 和哈希登记；不在无 await 的 commit 原子边界中写文件或等待网络。队列不能随原 response 被替代而删除此前合法提交的证据。artifact 持久化完成后该版本才标为 evidence_ready 并允许答案引用。写入失败中止 trial，不回滚已合法 commit，也不声称该版本可重建。冻结后最多等待 15 秒使必需证据 ready，失败记 evidence_persist_failed；答题计时要求冻结渲染与必需证据均完成。不得通过重跑当前查询伪造历史版本。

最终答案导出中去掉模式、输入来源和对话，只保留匿名编号、中性格式的答案与证据附件；人工检查内容中可能泄露条件的表述，不保证绝对盲化。过程编码包含授权语义材料，不能宣称完全盲化。在线模型不生成研究真值标签。

## 9 任务与排程

新增 manifest `experiments/olist_voice_text_study_v1.json`；保留旧 `olist_pilot.json` 和历史任务池。首次任务集合固定为 regional-delivery-risk、delivery-period-change、freight-definition-robustness、freight-attribute-association；其他两池保留作练习或后续研究，不混入本轮正式分析。

新 manifest 的英文任务是开放业务目标，不要求按顺序切换均值/P90、改变阈值或打断。同步作者中文说明。现有 task pool 的未提交修改不作为隐式冻结来源；实施者根据已审阅的版本创建独立材料，并明确来源哈希。

`prepare_study.py` 在收集前生成确定排程；每人四个不同任务、voice/text 各两个，同一模式连续两题，六人 voice-first、六人 text-first。任务与模式轮换，每项任务每模式六次；尽量平衡每个位置并输出实际平衡表，不声称完全消除了学习效应。固定随机种子、排程哈希和分配算法版本。默认拒绝覆盖现有排程。

`audit_study.py` 按 assignment/attempt 对账 12 人与 48 个计划 trial。重试不增加计划参与者或 trial 分母；实践记录明确排除，原失败保留。区分完整采集、技术有效、答案缺失和研究排除，软件不因答案差或无修订自动排除。

`export_study.py` 输出技术质检表、最终答案盲评包、授权过程编码包；使用安全投影，不把原始日志整段塞入 CSV。schema 和每份导出的访问范围有独立测试。

## 10 模块与子项目边界

| 子项目 | 修改与新增位置 | 独立交付 |
| --- | --- | --- |
| A 模态与统一输入 | conditions、main、realtime、prompts、runtime store、realtimePolicy、useWebSocket；新增 ConversationComposer | 真正的两模式完整请求链 |
| B 共享图表交互与渲染 | ChartSlot、Dashboard、chartSpecs、selection、tools；新增 interaction_context、窄 action dispatcher 与 render tracker | 指代、直接操作与版本化渲染证明 |
| C 任务与研究数据 | 新增 study、study_store、StudyPanel、manifest 和三个 study 脚本；扩展 trace/analyzer | 有界 trial、答案、排程、对账与导出 |

这是三个可独立测试但存在接口依赖的子项目。先冻结 A 的上下文与消息契约，再实现 B，C 可在契约稳定后分段交付。不要让多个实现代理同时写 main.py、realtime.py、trace.py 或 useWebSocket.js；共享接线由一个整合负责人完成。仅可并行独立测试、只读审查或不重叠模块。

既有五类分析工具和 Olist 数据语义不重写。只读图表 tooltip 不需要模型。缺密钥时前端可使用明确标记的本地 fixture 做组件测试，不得伪装为真实语音结果。

## 11 验收矩阵

| 编号 | 要求 | 必须提供的证据 |
| --- | --- | --- |
| A1 | 模态与旧 condition 独立 | 参数化测试覆盖四种组合；本 study 两模式固定 revision_enabled |
| A2 | 文字不触发录音/音频等待 | 浏览器权限与 provider 事件测试；真实 text 请求及多批工具 follow-up 完成 |
| A3 | 输入一致且幂等 | 重复 client_event_id、不同载荷冲突、错模式输入、中文 IME 与断线发送测试 |
| A4 | 服务端模式和 trial 权威 | 伪造 URL/消息条件无法切换；练习与正式 session 不继承模型历史 |
| B1 | 选择语义准确 | bar 类别、heatmap 行列、分箱边界、聚合列不被误当 raw filter；过期 selection 拒绝 |
| B2 | 鼠标不旁路事务 | 查询中点击筛选、直接 undo、冻结交错时旧结果不能覆盖；hover 不撤销请求 |
| B3 | 图表元数据可读 | 两种桌面尺寸、长标签、缺失、采样、固定基线和热力图真实浏览器检查 |
| B4 | 渲染证明不虚构 | init、多图、失败、空面板、旧代、分页和伪造 ACK 的测试 |
| C1 | 截止原子性 | pre-commit、音频派发、ASR 返回与 deadline 交错；到期后的 effect 不发布 |
| C2 | 持久化与失败恢复 | 答案重复提交、落盘失败、重启、刷新、新 attempt、completed 后断线测试 |
| C3 | 12 人排程可审计 | 48 个计划 trial、每模式每任务计数、唯一 ID、顺序及覆盖保护自动检查 |
| C4 | 研究材料可评分 | 固定证据引用、人工盲评样例、无语义同意时数据不泄露、无自动意图真值 |
| C5 | 历史兼容 | v2 fixture 和旧 pilot 排程/审计回归；新 v3 strict audit 不伪造缺失值 |

验收分四层报告：软件测试、真实数据口径、真实 provider 两模式预飞、参与者研究。不得把前一层通过写成后一层已经成立。现有 Python 与前端测试必须全部回归；此文不沿用旧测试数充当新结果。

## 12 文档与冻结

实现时在 worktree 中维护当前研究的中文说明、英文任务、评分规则草案和全会话编码手册。旧 REVISION_CODEBOOK 保持历史 in-flight 单位，新编码手册单独版本化并标明指标变化仍按语义规则判断，不能凭一次工具切换自动标为 Goal。

更新 README、PROGRESS、STUDY_FREEZE_CHECKLIST，明确本研究比较 interaction_mode，旧研究比较 revision policy。将主目录 agent.md 的协议与隐私约束同 worktree 的英文产品、中文作者文档和桌面原则协调为一个适用说明；不得直接覆盖主目录未提交材料，整合前审查差异并保留旧研究记录。

正式收集前固定 manifest、任务时限、同意范围、问卷、评分规则、排除与重试政策、主要指标及版本身份。两种模式的真实预飞失败、关键渲染或记录缺失、数据含义错误均禁止正式收集；自然 in-flight 修订稀少本身不构成本研究的技术失败，不诱导参与者制造修订。

完成本设计审阅后，实施计划应把 A/B/C 拆成有测试、文件所有权和明确整合点的任务。执行方式按用户要求采用子代理；本地提交限定本任务改动，不自动合并、推送或公开研究材料。
