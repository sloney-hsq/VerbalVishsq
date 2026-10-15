# VerbalVis Olist Pilot 运行手册

这份手册用于把当前软件实现运行为可审计的实验室 pilot。它不代替研究伦理审批、知情同意、样本量估计或统计分析计划。在招募参与者前，导师和研究团队应先固定这些内容。

## 1. Pilot 验证什么

Pilot 只验证三件事：

1. 指定的 Qwen Realtime 模型真实确认 `create_response=false` 和 `interrupt_response=false`，两种条件均能完成真实 Olist 分析。
2. 参与者在不被提示“请打断”的情况下，是否会自然产生 in-flight analytical revision，以及 revision 发生时旧请求所处阶段。
3. Trace v2 能否完整回收 context、request lifecycle、batch outcome 和 dashboard commit，且离线分析器不产生数据质量诊断。

Pilot 不用于宣称用户效益、任务效率或 TVCG 假设已经成立。

## 2. 固定实验对象

正式 trial 使用 [experiments/olist_pilot.json](experiments/olist_pilot.json)。其中只有两个开放式探索任务：配送风险和运费负担。任务要求识别现象、继续调查并用图表支持结论，但不指定固定的语音命令、工具调用次序或唯一答案。

两种规范条件是：

- `turn_taking`：当上一个 analytical request 仍 in flight 时，新的分析请求不进入执行。
- `revision_enabled`：允许新请求进入；旧请求未提交的 effect 失去提交和发布权。

两种条件必须共享同一 model、voice、prompt、dataset/config、tools、dashboard、前端和设备。不得为某一条件人为添加延迟。

## 3. 首次实验前检查

从本目录安装并验证：

```powershell
python -m pip install -e .
python -m pytest tests -q
cd frontend
npm ci
npm test
npm run build
cd ..
```

将 Olist CSV 放到 `configs/olist.json` 的 `dataset.data_dir`，再设置运行环境：

```powershell
$env:VERBALVIS_CONFIG = 'configs/olist.json'
$env:DASHSCOPE_API_KEY = '<lab credential>'
$env:QWEN_REALTIME_MODEL = 'qwen3.5-omni-plus-realtime'
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --workers 1
```

密钥只放环境变量，不写入 config、排程文件、Trace 或屏幕录制。本系统只支持单进程、单活跃实验会话；禁止使用多个 Uvicorn worker。

开始参与者 trial 前，先做一次不记入正式数据的技术预飞：

1. `GET /api/health` 返回 `status=ok` 和 `session_active=false`。
2. `GET /api/dataset` 返回 `dataset_id=olist`。
3. 连接界面后没有 provider contract 错误，初始五张图全部出现。
4. 用语音创建一张图，确认浏览器收到 dashboard commit；关闭连接后 health 恢复 `session_active=false`。
5. 分析新 Trace；若有 diagnostics，不得开始正式 trial。

## 4. 生成参与者排程

按招募顺序循环分配 `S1`、`S2`、`S3`、`S4`，不要在实验中临时随机。四个序列同时平衡条件先后与任务先后。参与者 ID 必须是伪匿名 token，不得包含姓名、邮箱或学号。

```powershell
python scripts/prepare_pilot.py `
  --manifest experiments/olist_pilot.json `
  --participant-id P001 `
  --sequence-id S1 `
  --base-url http://127.0.0.1:8001 `
  --output pilot_sessions/P001.json
```

工具会拒绝非规范 condition、未知 task、非法 ID、带 query/credential 或非法 host/port 的 base URL，以及意外覆盖既有排程。只有明确需要重生成时才使用 `--force`。输出保存 `manifest_version` 和规范化内容的 SHA-256，用来确认某个 trial 实际采用的任务/序列版本。`pilot_sessions/` 默认被 Git 忽略。

## 5. 标准化 trial 流程

1. 实验员先确认知情同意和当前 Trace consent 设置。此时**不要打开正式排程 URL**。
2. 正式计时前，用独立 practice context 熟悉麦克风、图表卡和两种输入规则。每个 practice 均使用独立 WebSocket session，`task_id` 使用 `practice-turn` / `practice-revision`，`trial_id` 使用 `<participant>.p1` / `<participant>.p2`；condition 顺序与该参与者的正式序列一致。Practice 结束后关闭页面，确认 `/api/health` 已恢复 `session_active=false`。Practice Trace 保留为技术记录，但按 `task_id` 明确排除，不与正式 trial 合并。
3. Practice 会话已完全释放后，才打开排程中当前正式 trial URL。这会创建新 Trace、新 provider session 和初始 dashboard，不继承 practice 的 dashboard 或模型历史。
4. 逐字展示该 trial 的 `prompt`。实验员可解释设备使用，不可建议指标、工具、图表或“应该打断的时机”。
5. 参与者宣布完成或达到预先写入研究方案的时限时结束。时限必须在首名正式参与者前固定。
6. 关闭当前页面，确认 health 中会话已释放，再打开下一正式 trial URL。新会话会从同一初始 dashboard 开始。

`trace_consent=false` 时仍会记录分析所需的 ID、阶段、时序和 outcome，但 transcript 和 arguments 脱敏，原始音频始终不保存。如果研究方案需要人工编码语义修订，必须单独取得同意并明确保留期，才能改为 `trace_consent=true`。

## 6. 中断、重试与排除

不要修改原 Trace，也不要将两次重试拼成一个 trial。如果出现 provider 断开、Trace 写入失败、浏览器刷新、实验员干预或数据配置错误：

1. 停止该 trial，保留已有 Trace。
2. 在独立的排除记录中写入 participant/trial ID、时间和预先定义的 reason code，不要在 Trace 内追加手工事件。
3. 是否重试按招募前固定的方案执行；重试必须使用新 trial ID，且分析时不与原 trial 合并。

## 7. 每日导出与质检

将 Trace 保留在不同步到 Git 的受控实验目录。对当日每个文件执行：

```powershell
python scripts/analyze_traces.py traces/<trace>.jsonl `
  --output pilot_sessions/<participant>-<trial>-summary.json `
  --strict
```

`--strict` 返回非零表示有 diagnostics，不是“可以忽略的 warning”。实验员至少检查：

- context 中 participant/trial/task/condition 与排程一致；
- `duration_complete=true`；
- 最后一个接受请求有 terminal state；
- dashboard commit、superseded batch/call 计数与实验观察不存在明显矛盾；
- `revision_saving_window_ms=null` 被解释为“没有可观测窗口”，不是零等待收益。

对每日全部正式 trial，还必须把排程与 Trace 批量对账：

```powershell
python scripts/audit_pilot.py `
  --schedules pilot_sessions `
  --traces traces `
  --output pilot_sessions/daily-audit.json `
  --strict
```

对账器以 `(participant_id, trial_id)` 为唯一单位，检查缺失、重复、计划外 trial、task/condition/dataset 错配、不完整会话、无 accepted request、无 final state 与 analyzer diagnostics。`practice-*` 会话只单独计数，不会被当成正式 trial。输出只使用 analyzer 的安全投影，不读取或回显 transcript、tool arguments、prompt、URL 或音频。

## 8. Pilot 结束门槛

只有在以下条件满足后才冻结正式实验版本：

- 真实 provider 与麦克风/扬声器路径可重复完成两种条件；
- 两个正式任务都能产生多步数据探索，而不是单次问答；
- Trace strict analysis 无 diagnostics，失败 trial 可由预定义 reason code 解释；
- 观察到的 in-flight revision 足以证明问题存在；若几乎不发生，应重新评估研究问题，而不是人为教参与者打断；
- 已固定正式任务时限、重试/排除规则、主观量表、事后 revision coding scheme 和统计分析计划。

事后语义编码的分析单位、类别、排除规则和一致性流程见 [REVISION_CODEBOOK.md](REVISION_CODEBOOK.md)。

冻结后只允许 critical bug、logging 或实验安全修复；每次变更均需重新标记版本并说明受影响的 trial。
