# Analytical Intent Revision 事后编码手册

本手册用于分析 VerbalVis 中的 in-flight analytical revision。这是**事后研究编码**，不是在线路由、权限或工具准入规则。运行时仍只区分 `empty`、`backchannel`、`stop` 和 `analytical_request`。

## 1. 分析单位

一个待编码单位必须同时满足：

1. Trace 中存在 `revision.received`，且 `data.in_flight=true`。
2. 新 request 在旧 request 的 `reasoning`、`tool_execution`、`committing` 或 `speaking` 阶段到达。
3. 它已被 runtime 接受为新 analytical request，而不是被 `turn_taking_busy` 拒绝的输入。

编码单位的唯一键为 `(session_id, request_id)`。一句话中含有多个变化时，仍是一个 revision；可以有多个 secondary code，但只能有一个 primary code。

如果 `trace_consent=false`、没有可授权的转写或录像，语义标签记为 `not_codable`，不得根据工具名称、最终图表或研究者直觉倒推。

## 2. Primary code

### G：Goal / intent correction

用户改变了分析想要回答的核心问题或所需结论。例如：从“哪个州延期最严重”改为“是哪些 seller 导致的”；明确纠正系统对问题的理解；或放弃原目标转向新问题。目标不变、只缩小范围时不编为 G。

### S：Scope / target-entity revision

核心问题不变，但修改了分析对象、时间、粒度、筛选、度量或对比集合。例如：从全国改为只看 SP；从按月改为按周；从所有品类改为两个品类；或把目标实体从 state 切换为 seller，但仍回答同一履约问题。

### H：Hypothesis / explanation revision

用户在看到系统讲解或图表后，改变了对原因、关系或机制的猜想，并要求新证据。例如：从“可能是配送距离”改为“会不会是某些 seller”；看到重量并不高后，转向检验体积或订单价值。必须能识别原猜想和新猜想；只是“再看一个指标”不自动属于 H。

### P：Presentation-only revision

分析对象、问题、假设和指标均不变，只修改图表类型、标题、排序、高亮或布局。P 仍是已接受 analytical request，但在报告中应与 G/S/H 分开。

### U：Unclear / not codable

转写歧义、上下文不足、多个变化无法判定主要目的，或 consent 不允许访问语义证据。U 不等于“没有 revision”。

## 3. Secondary code

可多选：`entity`、`time_range`、`granularity`、`filter`、`comparison`、`metric`、`explanation`、`visual_encoding` 和 `correction`。`correction` 表示用户明确指出误解、误听或错误实体；它可与 G/S/H 中任一 primary code 并存。

## 4. Primary 决策顺序

1. 核心要回答的问题是否改变？是 → G。
2. 是否因新证据而替换原因/关系假设？是 → H。
3. 是否只改变对象、范围、粒度、筛选、对比集或度量？是 → S。
4. 是否只改变呈现？是 → P。
5. 证据是否不足？是 → U。

## 5. 排除项

附和/backchannel、纯停止指令、空转写、ASR failure、被 `turn_taking_busy` 拒绝且未形成新 request 的输入，以及前一 request 已 settled 后的普通后续分析，都不纳入语义 revision 统计。它们可用于交互负担或识别错误分析，但分母必须与 in-flight analytical revision 分开。

## 6. 编码表字段

```text
codebook_version
session_id
participant_id
trial_id
condition_blinded_id
request_id
previous_request_id
previous_phase
primary_code
secondary_codes
codable
evidence_note
coder_id
adjudication_status
```

`evidence_note` 只记录最小必要判断依据，不复制长转写。编码文件与参与者身份映射分开保存。

## 7. 一致性流程

1. 两名 coder 先用正式数据之外的样例讨论本手册，然后固定 `codebook_version`。
2. 将 session/request ID 替换为盲化编号；如语义判断不需要 condition，不向 coder 显示 condition。
3. 两名 coder 独立编码预注册的全部或抽样数据。
4. 对 primary code 计算名义分类一致性，并同时报告原始一致率和每类混淆情况，不只报告一个总分。
5. 如修改 codebook，对受影响数据全部重编，不只修改冲突行。
6. 独立编码完成后才 adjudicate；保留两份原始编码和最终裁决。

## 8. 与 Trace 的分工

Trace 直接给出 in-flight 标记、previous phase、request/response/batch/call 关联、superseded outcome、真实 dashboard commit 与可观测时间间隔。人工只编码 Goal、Scope、Hypothesis、Presentation 和 secondary subtype。不得用人工编码覆盖系统事实，也不得让在线 Agent 生成论文真值标签。
