# VerbalVis 正式实验冻结清单

本清单用于把一次正式研究 wave 绑定到确定的软件、任务、配置和分析规则。勾选完成不等于研究有效，也不替代伦理审批、样本量论证或导师批准。

## 1. 研究决策

- [ ] 伦理审批或 waiver 已完成，版本与日期有记录。
- [ ] 招募、纳入/排除、退出、补偿、数据保留和删除规则已固定。
- [ ] 样本量依据、主要研究问题、主要/次要结果变量与统计分析计划已在看数据前固定。
- [ ] 两个条件只改变 revision policy；模型、提示词、数据、工具、TTS、界面和任务保持一致。
- [ ] 正式任务时限、练习流程、失败 reason code、重试和中断实验规则已固定。
- [ ] 主观量表及其语言版本、计分方法和施测顺序已固定。
- [ ] `REVISION_CODEBOOK.md`、coder 培训样例、盲化、双人编码范围与裁决规则已固定。

## 2. 软件与配置身份

- [ ] 从干净仓库根发布，而不是从包含其他项目改动的父目录运行。
- [ ] 记录 commit/tag、Python/Node 版本、依赖锁定结果和部署机器标识。
- [ ] 记录 `experiments/olist_pilot.json` 的 `manifest_version` 与 SHA-256。
- [ ] 记录实际 `VERBALVIS_CONFIG`、模型名称、provider endpoint 和非敏感运行参数；密钥不得进入记录。
- [ ] S1–S4 排程均由 `scripts/prepare_pilot.py` 生成，未手工改写 URL 或条件。
- [ ] `python -m pytest tests -q`、`npm test` 与 `npm run build` 在冻结版本通过。

## 3. 真实环境预飞

- [ ] 真实 provider 明确确认 `create_response=false` 与 `interrupt_response=false`。
- [ ] `turn_taking` 和 `revision_enabled` 均完成端到端语音、工具、dashboard、播放与关闭流程。
- [ ] Practice、正式 trial 1、正式 trial 2 使用三个相互隔离的 session。
- [ ] 旧 response 在 reasoning、tool execution 和 pre-commit 阶段迟到时都无法覆盖当前状态。
- [ ] playback ACK、dashboard commit、request terminal 和 session close 在 Trace 中可见。
- [ ] 实验员已演练 ASR failure、provider disconnect、浏览器刷新和 trial 重试流程。

## 4. 数据与隐私

- [ ] participant 身份映射与伪匿名 ID 分开保存；排程、Trace 和编码表不含直接身份信息。
- [ ] `trace_consent` 与知情同意一致；未同意时不进行依赖转写内容的语义编码。
- [ ] 原始音频默认不保存；如研究确需保存，目的、权限、保留期和删除流程已单独批准。
- [ ] `.env`、Trace、排程、participant data、raw audio 和真实 Olist CSV 不进入 Git。
- [ ] 数据备份、访问控制、传输、删除和 incident response 责任人已确定。

## 5. Pilot Go/No-Go

- [ ] 两个任务在两种条件下都能产生多步探索，不是单次问答。
- [ ] `scripts/analyze_traces.py --strict` 对有效 pilot trace 为 0 diagnostics。
- [ ] `scripts/audit_pilot.py --strict` 对排程与全部正式 pilot trace 为 0 diagnostics。
- [ ] in-flight revision 自然发生且数量足以支持研究问题；若几乎不发生，结论为 No-Go，而不是诱导参与者打断。
- [ ] pilot 发现的问题、修复版本及受影响 trial 已记录；修复后重新完成预飞。
- [ ] 导师和研究团队签署 Go 决策，并记录冻结日期。

## 6. 冻结后的变更控制

正式数据收集开始后，只允许 critical bug、logging correctness 或实验安全修复。每次变更必须：

1. 新建版本/tag，不覆盖旧版本；
2. 记录修改原因、代码差异、配置差异与受影响 trial；
3. 重跑全部自动化验证、真实环境预飞和排程/Trace 对账；
4. 由研究团队决定旧数据是否排除、分层或重收，不在分析后临时选择。

任何 task、prompt、模型、tool schema、condition policy、指标定义、questionnaire 或 codebook 变化，都应视为新的 study wave，而不是无记录的修补。
