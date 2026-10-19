## Task 6 C 审计与安全导出

**Files:** 新 audit_study.py、export_study.py、test_study_audit.py、test_study_export.py；复用 analyze_traces.py 公开入口，不改 v2 语义。

**Interfaces:**
- audit_assignments(schedule: dict, attempts: list[dict], trace_summaries: list[dict]) -> dict：planned、started、completed、aborted、missing、diagnostics；唯一分母是 assignment，practice/attempt 单列。
- export_study(study_root: Path, output_dir: Path, *, package: str) -> dict：package=technical/ratings/process；独立白名单，默认拒绝覆盖。ratings 无 condition、transcript、延迟、直接身份；process 尊重 transcript 同意。

- [ ] 写 test_audit_counts_assignments_not_attempts，重复/缺失/condition不符/同人第二正式任务报诊断；题目暴露后重试不能变成另一个有效独立样本。有效 empty 与 aborted 缺失区分。
- [ ] 写 test_blinded_ratings_export、test_process_requires_transcript_consent、test_unready_or_cross_attempt_evidence_ref_rejected；未授权字段、路径和原始日志不得出现。
- [ ] 运行新增专项 RED 后实现；StudyStore 元数据与 v2 session 汇总做一致性校验，不把一个 session 拆成多个独立样本。对账时 expected 12/6/3，观察缺失则报告实际数量，不补零伪造效果。
- [ ] 运行专项及 tests/test_trace_analyzer.py、test_pilot_schedule.py、test_pilot_audit.py 回归 GREEN；只提交所属文件。现有统计脚本不用于冒充人工论证评分，自动推断语义/研究真值不在范围。

## 主代理验收与研究冻结

- [ ] 自查所有 Task 接口一致、文件无交叉写、用户原有改动保留；独立审查修复回给对应 owner。
- [ ] 完整 .venv/Scripts/python.exe -m pytest tests -q；frontend 的 npm test、npm run build；更新本轮实际结果。上一轮基线为 370 passed/1 task-pool 断言失败、frontend 90 passed，不能把它写成本轮通过。
- [ ] 用合成伪匿名 ID 执行 prepare_study --manifest experiments/olist_voice_policy_between_v1.json --participants 12 --seed 20261019 --output study_schedules/cohort.json；验证 12/6/3、覆盖保护和 hash。生成物不提交。
- [ ] 使用合成故障 fixture 运行 audit_study --schedule ... --study-data ... --strict 和三个 export package；并非正式采集结果。
- [ ] 两题×两条件做真实数据/真实 provider/实际浏览器预飞，检查模型、手动响应确认、follow-up、自然播放结束、回声、冻结与回收。缺凭证则报告未验证，不开始正式采集。
- [ ] 更新 README、作者手册、冻结清单和本计划勾选；评分 oracle、问卷文本及全会话编码规则在首位参与者前校准冻结。只用分配条件练习，无第二条件训练。
- [ ] 本地交付，不合并、不推送、不创建新中间报告；本计划的最终验收小节记录摘要即可。
