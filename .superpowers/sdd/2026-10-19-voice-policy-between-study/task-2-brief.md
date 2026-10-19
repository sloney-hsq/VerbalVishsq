## Task 2 C 持久化与证据队列

**Files:** 新 study_store.py、test_study_store.py。

**Interfaces:**
- StudyStore(root: Path)；begin_attempt(assignment: dict, session_id: str, consent: dict, provenance: dict) -> dict，返回新 attempt_id 与 phase。
- apply_event(attempt_id: str, client_event_id: str, event_type: str, payload: dict) -> dict：短事务内登记幂等哈希、状态/答案/问卷变更及回执。
- append_event(attempt_id: str, event: str, metadata: dict, now_ns: int) -> None：白名单 study journal，带 seq/schema_version/session_id；不替代 Trace。
- enqueue_evidence(attempt_id: str, snapshot: dict, provenance: dict) -> str：同步深拷贝并入有界队列，不写磁盘；返回 job_id。
- async flush_evidence(attempt_id: str) -> None；evidence_ready(attempt_id: str, revision: int) -> bool；recover_incomplete() -> list[str]。后台 worker 为 study 所有，不随 response 取消。

- [ ] 写 test_answer_idempotency_and_conflict，断言相同 submission_id/内容只有一条答案、异内容不覆盖；test_evidence_refs_are_ready_and_attempt_local 拒绝外部/未落盘版本；test_completed_survives_disconnect 不反转终态。
- [ ] 加 test_evidence_quota_and_failure：恰好 50 MiB 可存、再多一字节 evidence_limit、写入异常不 ready；test_consent_categories_separate 未授权转写不泄露且已授权答案正常保存；test_restart_aborts_incomplete 保留所有旧记录。
- [ ] 运行 .venv/Scripts/python.exe -m pytest tests/test_study_store.py -q，确认 RED。
- [ ] SQLite 表至少包含 attempts、study_events、client_events、answer_drafts、answers、questionnaires、evidence_artifacts。答案先事务提交再 Saved；草稿版本递增；draft/submit 内容总长 8000；问卷只收 continuity/control/effort/waiting_interference 四项 1–7 整数，题项与锚点固定为设计 §5.2。写 artifact 使用同受控目录临时文件、原子替换、内容 hash 后登记，拒绝路径逃逸；队列/容量/写入故障可查询并由 A 中止 trial。
- [ ] 运行专项 GREEN，人工检查无 raw audio/自由日志拷贝；只提交所属文件。

