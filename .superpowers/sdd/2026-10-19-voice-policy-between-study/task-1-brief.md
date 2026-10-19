## Task 1 C 固定任务与分配

**Files:** 新 study_manifest.py、manifest、prepare_study.py、test_study_schedule.py；更新 test_study_flows.py 和 .gitignore。

**Interfaces:**
- validate_manifest(payload: dict) -> dict：校验 schema_version=1、design=between_subjects、study_version、两个规范条件、两任务、时限和同意要求。
- prepare_cohort(manifest: dict, participant_ids: list[str], seed: int) -> dict：返回 schema_version、algorithm_version、seed、manifest_sha256、assignments 和 balance。
- assignment 字段：assignment_id、participant_id、trial_id、task_id、condition、dataset_id、study_id、study_version、manifest_sha256、is_practice=false；attempt_id/session_id 在开始会话时生成，不在排程中重用。
- load_assignment(schedule_dir: Path, assignment_id: str, dataset_id: str) -> dict：只查配置目录内已校验排程，未知/重复/数据集不符拒绝；不拼接客户端路径。

- [ ] 写 test_balanced_single_trial_cohort：assert len(assignments)==12；每 participant 1 条；每 condition 6 条；每 task×condition 3 条；同 seed 相同结果。覆盖重复 ID、13 人、非法条件、未知任务、路径穿越和覆盖既有输出拒绝。
- [ ] 运行 .venv/Scripts/python.exe -m pytest tests/test_study_schedule.py -q，确认新增能力缺失 RED。
- [ ] 按设计 §3 两阶段随机分配实现，默认 seed=20261019，algorithm_version=task-block-randomization-v1；保存 Python 版本与排程规范 JSON 哈希。复制当前 pool 2.0 的英文材料，不改写其原文；逐任务哈希明确只对 prompt UTF-8 计算，manifest 哈希排除自身 hash 字段。
- [ ] 将旧 test_task_pool_has_six_open_ended_tasks 改为两任务 2.0 的 ID/title/范围/口径断言；保留 test_six_task_replay_uses_real_toolbox_state 原有六回放断言。已有 pool 文件由主代理单独审阅后纳入本任务，不回退为六题。
- [ ] 运行 Task 1 测试及 test_study_flows.py 全部 GREEN；只提交所属文件，记录新分配契约。

