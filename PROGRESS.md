# Historical execution ledger

## 2026-10-19 公开开发快照上传授权

维护者明确确认：除 `backend/.env.example` 外，上传当前隔离 worktree 的全部文件到 `sloney-hsq/VerbalVishsq` 的开发分支，不覆盖 main；已告知目标公开及产物范围。按此最新指令，根 `.gitignore` 仅保留这一条排除；本次快照包含依赖、缓存、合成语音与本地开发产物，不作为精简发行包或正式实验冻结版本。早先“日志与预飞目录均受 Git 忽略保护”的描述不再适用于此快照。历史运行记录保留原文，不能据此推断当前模型语义执行已稳定。

## 2026-10-19 可读完整会话日志与工具关联

按用户确认的范围新增 `backend/conversation_log.py`，通过真实 `AnalysisSession` 发布和工具批次路径接入。每会话独立 `conversation.jsonl` / `tool_calls.jsonl`，保留旧格式的 `ts`、`session_id`、`role`（You/AI）、`text`；增加消息、request、response、batch、call 关联。用户最终转写去重，AI 已发布流式文字在完成、打断或断连时合并落盘并 flush。工具保留参数（敏感字段脱敏）、耗时、实际执行与批次提交状态，失败/取代不伪装提交；revision 固定为本次提交快照，而非后来状态。纯工具响应不强造 AI 文字消息，follow-up 以相同 request_id 关联。

默认关闭，要求配置开关与本会话文字记录同意同时成立。正式研究仍使用冻结的服务端 `study.consent.transcript`，未更改实验默认同意；Trace v2 与分析器不变。初始化失败明确拒绝开启会话，运行中写入失败提示归档可能不完整。不保存音频、密钥、供应商原始包或完整数据行；没有新增回放网页，也不能恢复过去未记录的对话。文字发布不等于实际音频听完；强杀进程时未结束的缓冲文字不保证恢复。

专项 **19 项**覆盖完整长转写、流式合并、打断/Stop/断连、迟到和未发布输出、真实批次路径、回滚/跳过/取代、版本关联、同意门控、初始化及写入故障。首轮全量 493 通过；随后 `.gitignore` 被并发覆盖导致两项数据保护测试失败，保留新增密钥规则并补回保护规则后，最终 Python 全量 **495 passed**（1 个既有 Starlette 弃用提示）。Node **20.19.0** 前端 **141 passed**，production build 成功（既有 Vega chunk-size 提示）；`git diff --check` 通过。默认日志与本地预飞目录均受忽略规则保护。

按用户授权在验证后启动新代码的 **8002** 服务，仅其忽略目录内的演示配置开启 `conversation_logging` / `trace_consent`。真实 Qwen + Olist 合成语音探针记录 **1 条最终用户 ASR + 1 条 AI 回复 + 1 次真实工具调用**，产生 dashboard revision 1；已核对归档文字与实际发布文字完全一致，工具 session/request/user_message 关联一致。本轮探针不是参与者数据，无真人麦克风、真实扬声器或浏览器实际渲染验收，不证明自然连续对话已稳定。真实应用新会话已就绪，麦克风停止，等待用户主动开始。日志留在 `.superpowers/realtime-preflight/conversation_logs/<session_id>/`，未提交、合并或推送。

## 2026-10-19 请求级执行依据与一次性纠正（真实语音仍未完全通过）

按用户确认的最小范围修改 `backend/realtime.py`、`backend/prompts.py`，新增 `backend/execution_grounding.py`。每次生成携带本轮原始请求、最新批次真实 commit_status/errors/revision 以及本轮是否有合法提交。模型仍自主选工具；进度语音仍流式，不等待用户批准，不把所有讨论转成工具调用。没有新增意图分类模型或提交权限来源。

回答结束且无工具调用时，保守匹配英文图表修改承诺与执行依据；无提交、失败或无变化的矛盾最多触发一次同请求纠正。再次矛盾则停止剩余播放，显示未验证提示，令本请求 failed、连接仍可继续接受输入。不会追回已听到的错误语音；提示为界面文字，不是保证播出的语音纠错。新问题、Stop 和研究截止仍由原协议控制，旧纠正不能重启或提交；两实验条件共用机制。该规则只覆盖有限句式，不验证任意表达、同一请求内每项修改的准确语义或真实渲染。

本轮进行了两次真实 Qwen + Olist 合成英文语音预飞，均不是正式实验：第一轮建图成功，改图参数不完整，批次 failed 未提交；模型承认失败后只说“我来修复”，未继续执行。该具体漏检先加入失败测试再修复。第二轮建图成功，改图只承诺不调用；一次自动纠正后仍只承诺，系统正确显示未验证并恢复 ready，但探针等待改图提交超时。没有把这两轮或重复尝试包装成完整成功，Stop 后恢复在本轮探针中未到达。

独立审查发现并修复普通“讲解重点”误判、先成功后失败的真实部分总结误判、以及明确无需更改仍被纠正的问题；对应测试先失败后通过，复审无开放阻断项。最终后端 **476 passed**（1 个既有 Starlette 弃用提示），其中新专项 **26 passed**；Node **20.19.0** 前端 **141 passed**、production build 成功（既有 Vega chunk-size 提示），`git diff --check` 通过。包含两条件相同防护、流式音频、只读/no-op、纠正期间 Stop/新请求竞态。

最新代码已重启在本任务隔离 worktree 的开发服务 **8002**；未改动用户的 8017 服务，未提交、合并、推送或启动正式 trial。结论是增加了有界恢复和诚实的失败出口，**并非彻底解决模型“只说不做”；完整真人语音、播放与渲染验收仍未通过**。

## 2026-10-19 正式图表组件的滚动条闪动修复

用户截图暴露此前内置浏览器验收未覆盖的传统占空间滚动条差异。使用同一生产 Dashboard/ChartSlot 在隔离诊断页复现：SVG 把 360.97px 容器宽取整为 361px 后触发横向滚动条，进一步挤占宽高并重新测量。修复直接落在正式 Vue 源码：ResizeObserver 测量 border-box；绘图宽高向下取整并留 2px 余量；typed/legacy 图形均采用含轴与 padding 的 fit autosize；固定格不再建立内部滚动容器，非固定图形的全量/兼容滚动保留，Vega 包装层使用 block。没有改变分析数据、尺度、编号、布局比例或渲染 ACK 条件。

回归测试先失败后通过，前端全量 **141 passed**，production build 成功（既有 Vega chunk-size 提示）。约 2048×1087 CSS 视口的传统滚动条复现场景中，九图横纵溢出均为零、SVG 文字无出界，初始 9 次 SVG 安装在后续测试/构建期间保持不增，分类分页仍可用。诊断页仅用于排错，不作为应用交付，已在结束时移除。

按用户要求展示正式源码和真实入口：先启动 8001 核对缺 Key 的显式错误，后发现并复用同一工程既有且已配置凭证的 **8002** 服务；关闭本轮多余的 8001 进程，未修改/读取密钥。最新 production bundle 由 `http://127.0.0.1:8002/` 提供，实际浏览器显示 **Ready / Start mic**，没有 Preview 模式或保存结果注入。此新会话初始 0 图，未代替用户发分析请求或开麦；未实测本轮真实语音生成图表，不将离线九图渲染验证冒充端到端语音验收。未合并或推送。

## 2026-10-19 Provider 配置超限修复与真实服务语音预飞（未完全通过）

在现有 `codex/visual-analysis-tools` 隔离 worktree 实施，未提交、合并、推送，也未启动正式实验。新增 `backend/provider_payload.py`：仅折叠完全匹配的重复 source schema，完整领域定义仍发送一次，本地 Toolbox 验证器不变；重复数据索引精确去重，dashboard 上下文明确省略 rows；所有 provider 消息以实际 compact JSON UTF-8 字节检查 256 KiB 上限。超大工具输出明确报告未交付结果，并保留真实 execution/commit/revision；大 metadata 或累计图表仍可触发上下文超限，此时明确失败并保留已经提交的状态。没有绕过 ResponseProtocol、逐次输出检查或原子 CAS。

实测真实 Olist 空 dashboard 初始化为 **112,099 bytes / 15 tools**，此前约 496 KB 的初始化触发 provider 1009 断连。该数值不是所有初始 dashboard 的大小保证。北京业务空间、当前用户配置的 `qwen3.8-omni-flash-realtime` 和密钥可连接，并确认 `create_response=false`、`interrupt_response=false`。旧本地音色 Ethan 虽获配置回执，却在生成时被拒绝；本地改用官方示例的 Tina 后收到真实语音。配置和密钥文件均留在本地忽略范围，未写入文档或测试。

使用 Windows TTS 的 16 kHz 合成英文 PCM，经真实应用 WebSocket、真实 Qwen 与真实 Olist 查询进行开发探针。已观察到柱状图 revision 1 → 月度折线图 revision 2、接受执行/播放生命周期中的新请求、旧响应停止通知、Okay 不触发修订、Stop 返回 ready。**完整探针仍失败**：多次自然改图和 Stop 后重命名出现只口头确认、无工具调用；另一轮工具参数不完整导致整个批次失败而未提交。加强提示词及明确说出工具名均未消除问题。诊断时，失败响应仅返回 message，没有 function-call-arguments 事件；正常调用在 arguments.done 和 response.done 中一致，未发现被遗漏的调用。不能从这些观察断言所有模型错误均已定位。

探针无真人麦克风、真实扬声器或浏览器实际播放/渲染，仅模拟 interrupted ACK，未模拟 natural-end ACK；故不证明声学全双工、回声抑制或用户可见完成。未执行正式 trial.start。开发配置没有 study，Trace consent=false，音频/诊断均在忽略目录 `.superpowers/realtime-preflight`，不混入正式数据。该目录 `launch.py` 从用户本地凭证文件读取密钥，启动 **8002**；旧的本任务 8001 预飞进程已停止。离线 5176 visual-check 页面不是该真实语音入口。

最终软件验证：Python **450 passed**（1 个既有 Starlette 弃用提示）；Node **20.19.0** 前端 **139 passed**、production build 成功（既有 Vega chunk-size 提示）；`git diff --check` 通过。本轮新增 10 项 payload 测试，核心缺陷按 TDD 先复现失败再修复；独立复审无开放 P1/P2。并发界面任务加入的视图编号及其测试已保留并包含于最终全量验证。

当前结论：配置超限已修复，真实服务的部分语音/工具路径可用；**自然连续对话与 Stop 后恢复尚未验收通过，不能开始正式实验**。下一步需单独确定行动规划/执行核验与语音确认的边界，不能靠删减本地校验、伪造提交或重复尝试到偶然成功来宣布稳定。

官方核对：[Realtime](https://help.aliyun.com/zh/model-studio/realtime)、[客户端事件](https://help.aliyun.com/zh/model-studio/client-events)、[Function Calling](https://help.aliyun.com/zh/model-studio/qwen-function-calling)。Realtime 不支持 `tool_choice` / `parallel_tool_calls`，未添加这些未支持参数。

## 2026-10-19 简洁 2×4 布局、语音视图编号与四分之一对话区

参考用户指定的 `F:/VerbalVis2 - 0705保存 - 副本/frontend`，采用单行顶栏、规整图卡和逐行底部转写，去掉重复 Preview 按钮、提示和空白引导。当前九图中，`freight_bins` 放回左侧，八图按两行四列等高等宽；右侧仅一张分类热力图跨两行。使用实际图卡剩余高度生成 Vega 图形，不缩放 SVG 或裁切数据；类别页随可读高度调整，全局域与原数据保留。额外视图或分面使用自然高度兼容布局，不静默丢图。修复小数间距导致非法网格行号，等高布局使用原生两行网格避免像素累积误差。

标题左侧增加 1–8 和右侧 9 的可访问序号，窗口缩放不改变映射；后端模型上下文与 inspect_dashboard 投影相同 display_number，语音引用要求按此映射解析到真实 ID，不改变权威状态、历史或提交机制。Conversation 按用户最新要求固定为视口高度 25%，保留完整转写与实验控制的面板内滚动，两条件共用同一界面。

验证：新增回归先失败后通过；Node 20.19 前端 **139 passed**，Python 全量 **449 passed**（1 个既有 Starlette 弃用提示），production build 成功（既有 Vega chunk-size 提示）。实际浏览器核对约 3840×2160、2560×1440、1920×1080 等效 CSS 视口：九图同屏、左侧等大、右图跨行、图内横纵溢出为零、1920 下 SVG 文字未裁切，对话区分别约 540/360/270px；1366×768 回退双列并保留九图与编号。热力图前后翻页可达剩余类别且维持右列。截图保存于忽略目录，临时视口已恢复。编号的真实语音/provider 会话尚未联调；未合并或推送。

## 2026-10-19 Conversation 移至底部

按用户要求将 Conversation 从右侧移到页面底部，分析画布占满宽度；保留五列及最右侧热力图布局。普通对话底栏约 140–240px，可收起；横向空间用于并排呈现同一轮中的话语，完整文本、分析步骤与修订反馈保留。实验准备、答题和问卷阶段自动增加底栏高度，保留原 study 控制和单独滚动。两条件共用同一布局，无语音、数据或协议改动。

为避免常见缩放下底栏挤出图表，可用宽度小于 2200px 的五列热力图改为每页 12 类，保留完整类别、全局尺度和颜色域。回归测试先失败后通过；Node 20.19 下前端 **133 passed**，production build 成功（既有 chunk-size 提示）。实际浏览器核对底栏位于分析区下方且宽度相同，4K 和 200% 等效视口下当前 9 图全部可见，无图内溢出或文字裁切；验证底栏收起/恢复，合成实验答题字段与提交入口仍可用。未实测真实语音，未合并或推送。

## 2026-10-19 紧凑五列与 4K 整屏画布

按用户最新要求改为左侧四列普通子图、最右一列热力图；多张热力图在右列依次排列，不修改 store 中的视图顺序。品牌、会话状态、视图数量与分析范围合并到约 44px 的单行工具栏，移除副标题、重复预览说明、分析区大标题、引导文案与重复页脚。图卡自身不再写入列定位，避免翻页后的组件更新覆盖网格定位。

宽屏使用类别分页并关闭全量展开，保留全部数据、全局色域与数值尺度。热力图取消固定最小宽度，按图卡宽度安排轴标签和色标；色标标题换行、渐变长度与刻度数自适应，窄图卡长类别标签增加倾角及底部预算。仅实际测量确认所有图卡落屏后关闭画布滚动，不靠裁掉图卡实现整屏。

验收：回归测试经历 RED/GREEN；Node 20.19 和 Node 24.14 下前端全量均 **132 passed**，两个版本的 production build 均成功（既有 Vega chunk-size 提示）。实际浏览器检查约 3840×2160、2560×1440、1920×1080 等效 CSS 视口（页面缩放导致部分尺寸有 1px 舍入差）：当前 9 图均完整同屏，五列定位正确，无画布或图内横纵溢出，SVG 轴/色标文字无边界裁切；验证类别页 1–20 至 61–73 可达及翻页后右列定位稳定。保留窄窗口兼容布局；未验证真实语音，未合并或推送。

## 2026-10-19 Node 20.19 兼容复验与真实预飞前置检查

下载官方 Node v20.19.0 Windows x64 便携包并按官方 SHASUMS256 校验，仅放在忽略目录 `.superpowers/runtime-node20`，未替换全局 Node。复现 Windows + Node 20 不展开 `tests/*.test.js` 导致 npm test 无法启动；将测试脚本改为 `node --test` 自动发现，兼容 Node 20.19 与现有 Node 24.14 的入口。

早期快照在 Node 20.19 下 131 项通过且构建成功；验证期间工作区新增 `scaled 4K heatmap legend retains its full title above a bounded gradient` 测试，随后两个 Node 版本均为 131 passed / 1 failed（titleOrient 实际 left、预期 top）。本轮未覆盖并发中的图例实现；此记录不宣称最新工作区全绿。当前进程、用户和系统环境均未设置 DASHSCOPE_API_KEY（只检查存在性），因此未启动真实 provider 预飞、未创建参与者记录、未推送 GitHub。

随后图例实现更新后，本轮再次使用 Node 20.19.0 运行完整 npm test：**132 passed / 0 failed**；此前最新 production build 亦成功，仍有既有 chunk-size 提示。Node 20.19 的测试入口兼容问题已修复，真实 provider 预飞仍未完成。

## 2026-10-19 子图头部与分页控件收紧

按用户确认的展示调整，将常规图表类型、指标摘要、结果行数和观测单位移入标题右侧的 `ⓘ` 详情入口（悬浮提示、点击或 Enter 展开、Escape 关闭）；普通标题区实测 28px。分页、全量/分页切换及类别范围组成右对齐紧凑行，保留完整无障碍标签。抽样、缺失、独立尺度、截断等分析提示保持可见。仅修改 ChartSlot 展示与对应回归测试，不修改数据、尺度、研究协议或 SVG 渲染配置。

验证：回归测试先失败后通过；前端全量 **125 passed**，production build 成功（既有 chunk-size 提示）。实际浏览器检查 1366×768、1920×1080、2560×1440、3840×2160 下的卡片头部和分页右对齐；验证前后翻页、显示全部、返回分页及详情键盘操作。临时视口已恢复，使用独立预览页验证，未操作用户答题字段。未 commit、merge 或 push。

## 2026-10-19 当前研究方案调整

用户确认采用 12 人组间设计：每人一道正式任务、只体验一种语音条件，全双工与 turn-based 各 6 人；任务池 2.0 的两题在每条件各分配 3 人。更新后的[研究设计](docs/superpowers/specs/2026-10-19-voice-policy-between-study-design.md)和[工程计划及最终验收](docs/superpowers/plans/2026-10-19-voice-policy-between-study.md)替代此前语音/文字与多 trial 方案。

本轮已由三个 GPT-5.6-Sol high 子代理完成实现并交叉复审，主代理在隔离 worktree 整合验收：固定 assignment、600/180 秒计时、15 秒冻结准备、真实渲染 ACK、证据与答案持久化、问卷、审计及三类安全导出。保留 ResponseProtocol 唯一授权、既有语音条件、Trace v2、任务池 2.0 和此前 4K 工作台改动；无新分析工具、文字输入或鼠标 mutation。答题区放在右侧独立滚动面板，图表保持可见。

本轮最终验证：Python **439 passed**（1 个既有弃用警告），前端 **125 passed**，production build 成功（既有 chunk-size 提示）；真实 Olist 15 步工具回放通过；12/6/3 排程、合成故障严格审计和三类导出 CLI 通过；实际浏览器 1920×1080、1366×768 验收通过。任务池原字节 SHA-256 保持不变。关键复审修复包括 Stop/Start 重放、旧页渲染回执、Start 原子曝光、证据/答题写入故障关闭和 missing assignment 诊断。

交付保留在 `C:/Users/admin/.codex/worktrees/visual-analysis-tools/VerbalVis`、分支 `codex/visual-analysis-tools`；本轮未 commit、merge 或 push。真实语音预飞未完成（进程无模型密钥），Node 20.19 兼容复验未完成（当前 Node 24.14.0）；正式冻结、伦理/同意及真实数据评分 oracle/双人校准仍待完成。合成 UI 和 provider double 不能冒充真人或真实语音证据。下文均为历史记录，不是当前版本的验收结果。

2026-10-12: User requested code completion after confirming dataset + interface scope. The approved TASKS.md work packages were executed; this ledger preserves integration decisions and historical verification evidence. Completed intermediate implementation checklists have been removed; consult the retained milestone reports and Git history for details. These dated results do not establish the status of the current checkout.

Ruling: work in the explicitly requested repository on the approved research snapshot; do not create a separate worktree or alter archived source. Existing extraction-script test failures remain separately reported.

| Shared boundary | Producer / consumer | Resolution |
|---|---|---|
| Task 1 → Task 2 | DatasetAdapter definitions/execute → Toolbox | dict result + columns metadata, trusted read-only adapter operations |
| Task 2 → Task 3 | Draft + commit → AnalysisSession | commit is synchronous; protocol guard held; no await |
| Task 1 → Task 3 | description/tools → prompts/session | generated descriptions, no domain conditionals |
| Task 2 → Task 4 | view snapshot → renderer | old view keys retained, columns metadata added |
| Task 3 → Task 4 | browser events | existing event names retained, sequenced input floor |
| All tasks | source ownership | only the approved implementation, no shared edits by implementers |

Task 1: complete, uncommitted; 23 scoped tests. Independent review findings (module lifetime, typed scalar/temporal cells) fixed and re-review clean.
Task 2: implemented; 28 scoped tests. Review found empty-dashboard date-filter value validation gap; assigned integration fix wave.
Task 3: implemented; reviewer found suspension during post-commit sends and failed/empty ASR policy gaps. Fix wave also covers late utterance correlation and under-lock effect validation.
Task 4: implemented. Frontend test/build and app HTTP/startup verified. Trace setup slot leak and ASGI cancellation cleanup fixed with regressions.
Task 5: execution/commit outcome contract and race tests complete; independent review approved. Live provider/human interaction not verified.

Ruling: dataset descriptor uses `version` as in DESIGN_ZH; tool results and dashboard snapshots use `dataset_version`. This is an explicit boundary mapping, not two versions.

Ruling: Qwen manual-response controls are required and must be echoed as false in session.updated. Official server examples include these keys, but client docs do not promise all models accept them. Unsupported endpoints fail closed instead of silently assigning automatic responses new authority. Live provider compatibility remains unverified until credentialed integration.

Task 3 progress: 6 protocol + 6 session + 2 trace/prompt tests pass; real WebSocket entry being integrated. No live Qwen validation yet.

2026-10-13 integration evidence before final fix wave: 70 new Python tests passed; frontend 34 tests/build passed (additional presentation tests subsequently added). App health, dataset metadata, static homepage: HTTP success; component style blocks identical to old source. Browser tool failed to initialize (kernel asset path missing), so no screenshot comparison claimed. Process environment DASHSCOPE_API_KEY absent (presence checked only, no secrets read).

Review coordination: dataset_implementation → data_contract_review (fixed/review clean); dashboard_tools → state_tools_review (one fix assigned); session/main → runtime_transport_review (concrete fixes assigned). integration_fixes owns only runtime/tools and associated regressions; the coordinating scope owns frontend/main/docs. Existing unrelated user files remain untouched.

Ruling: tests may use transport doubles to deterministically inject races; production always connects real Qwen and never substitutes fake responses. A green test suite does not establish live provider compatibility.

## 2026-10-13：开发主线收敛为三个 Milestone

用户明确要求停止同时扩展 protocol、dataset 与实验。`TASKS.md` 现在是唯一任务主线：M1 Analytical Backend → M2 Visual Analytics Runtime → M3 Research System。M1 期间冻结 `backend/dashboard.py` 和 `backend/response_protocol.py` 的功能扩展。

M1 当前证据：

- Olist adapter 拆为 `interface.py / schema.py / metrics.py / queries.py`；
- 9 张 raw tables 可独立读取；
- persisted `order_grain / item_grain / payment_grain / customer_grain / seller_order_grain`；
- canonical latest review 规则统一用于所有 review metrics；
- 公开数据集工具仅 `aggregate` 和 `compare_segments`；
- 旧 `compare_commerce` 测试调用已迁移；
- focused Olist tests：24 passed；
- full Python tests：121 passed / 1 既有 deprecation warning；
- frontend baseline：36 passed；production build 成功（仅 Vega bundle size warning）；
- 真实 Task A：SP weekly 27 rows / 15,495 orders；
- 真实 Task B：RJ office_furniture 212 orders vs bed_bath_table 1,357 orders。

迁移前历史记录：源工作区未创建 Git tag 或推送；独立仓库的 tag 和远程状态以当前 Git 记录为准。

## 2026-10-13：M2 Visual Analytics Runtime

- `specFactory.js` 现在只从 result `columns` 元数据获取 field type、label、unit 和 description；ratio/BRL/days/points/kg/cm3/count 采用通用格式规则，原始数值不被转成字符串。
- column description 保存在合法的 Vega-Lite 顶层 `description` / `usermeta`，不再写入非法 field definition；quantitative color 格式使用 legend。
- `highlightSpec.js` 只保留 x/series/color 通用别名，根据实际 columns/data 推断；不存在的 clause 组合不显示虚假高亮徽标。
- `ChartSlot.vue` 移除 low-score 阈值特判，样式和布局保持；metadata/spec 错误进入可见错误边界。
- Olist `initial_dashboard` 含 5 个普通 `create_chart` 参数，没有 rows。`AnalysisSession` 用同一 draft 执行 5 次正式 `create_chart → aggregate`，成功后只 commit 一次；失败整体 discard。
- 真实 Olist 验收：5 图行数 23/27/27/15/23，单位为 orders/points/orders/BRL/days，月份升序，Top 15 revenue 降序且 `truncated=true`。
- 最终测试数以本轮最后验证命令为准；真实 Qwen 仍因缺少 `DASHSCOPE_API_KEY` 未验证。

## 2026-10-14：M3 Task 6 离线分析器与整合验证

- 新增标准库 Trace v2 analyzer：按 session 独立汇总，输入按物理行容错、按 session-local `seq` 排序；报告坏 JSON、schema/context/timing 错误、重排、gap、重复与冲突。
- 指标只用 ID、canonical lifecycle/outcome、真实 dashboard commit 和 monotonic timestamps；consent-controlled transcript/arguments/audio/payload 不读入分析投影，也不回显。
- `revision_saving_window_ms` 仅使用实际观察到的 `previous_request_id` settled timestamp 计算；缺失、superseded、只有 `response.done` 或负差均返回 null，负差仅增加 diagnostic。
- analyzer 专项测试：44 passed；完整 Python：277 passed（1 个既有 Starlette/httpx deprecation warning）；frontend：63 passed；production build 成功（既有 833.94 kB embed chunk warning）。
- CLI fixture 输出为 1 个 session run、2 requests、1 个真实 dashboard commit、duration 1000 ms、last-request terminal latency 100 ms、0 diagnostics；真实 Olist initial-dashboard smoke：1 passed，使用配置的 9 CSV 数据目录。
- 完整命令、坏输入恢复与 review 状态记录在 `.superpowers/sdd/m3-research-system/reports/task-6-offline-analysis-verification-report.md`。
- Task 6 独立 review 发现并修复了跨 batch 复用 `call_id` 导致 superseded call 少计的 P2 问题；现以 `(batch_id, call_id)` 为自然键，最终复审通过。M3 软件实现已完成；带凭证的 Qwen 语音 pilot 与用户实验仍是外部验证边界。

## 2026-10-14：M4 Pilot Readiness

- `experiments/olist_pilot.json` 固定两项开放式探索任务和 S1–S4 四个交叉平衡序列；任务文本不进入 URL 或隐藏模型上下文。
- `scripts/prepare_pilot.py` 校验 manifest、规范 condition、伪匿名 token 与 base URL，为每个 trial 生成与 Trace v2 context 一致的 URL；默认拒绝覆盖既有排程。
- `PILOT_RUNBOOK.md` 固定预飞、标准 trial、失败/重试、每日 strict Trace 质检和 pilot Go/No-Go 边界。
- 新增 GitHub Actions、发布忽略规则、`CONTRIBUTING.md`、`SECURITY.md` 与 `RELEASE_CHECKLIST.md`。许可证、真实作者 citation、数据分发权和伦理材料仍需维护者明确决定，不由代码伪造。
- Pilot 排程专项回归：14 passed；完整 Python：291 passed（1 个既有 Starlette/httpx deprecation warning）；frontend：64 passed；production build 成功（既有 833.94 kB Vega embed chunk warning）。S1–S4 均成功生成排程，Trace fixture 在 `--strict` 下为 1 trial / 0 diagnostics，release hygiene checks 通过。最终独立复审发现并验证修复了 page URL 实验 context 未进入 WebSocket 和 practice/formal trial 共享 session 的两项 Important 问题；复审结论 `APPROVED`。

## 2026-10-15：Pilot evidence reconciliation

- 新增 `scripts/audit_pilot.py`：以 `(participant_id, trial_id)` 为自然键，将生成排程与 Trace v2 的隐私安全离线摘要对账；检测缺失、重复、context 错配、计划外、不完整、无已接受请求和无最终状态的正式 trial。
- Practice session 仅单独计数，不参与正式 trial 完成率；审计输出不复制 prompt、URL、transcript、tool arguments、audio 或原始事件。`--strict` 对任一诊断返回非零，输出文件默认拒绝覆盖。
- 新增 `REVISION_CODEBOOK.md`：人工只对已接受的 in-flight revision 编 Goal、Scope、Hypothesis、Presentation 或 Unclear；Trace 继续提供 phase、authority、commit 与 timing 事实，语义编码不进入在线控制路径。
- 新增 `STUDY_FREEZE_CHECKLIST.md`，将研究决策、版本身份、真实环境预飞、隐私、Pilot Go/No-Go 与冻结后变更控制分开列出；代码不能替研究团队勾选伦理、样本量和统计方案。
- `PILOT_RUNBOOK.md`、README、任务看板和发布检查表已接入批量审计与 codebook 冻结要求。
- 最终验证：Python 296 passed（1 个既有 Starlette/httpx deprecation warning）；frontend 64 passed；production build 成功（既有 833.94 kB Vega embed chunk warning）；审计相关专项 62 passed；Trace fixture `--strict` 为 1 trial / 0 diagnostics；S1–S4 均生成 2 个 trial；脚本编译和敏感产物/真实 Olist 数据忽略规则通过。
