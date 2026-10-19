"""Synthetic integration rehearsal, never participant data."""
import asyncio
import json
import subprocess
import sys
import uuid
from pathlib import Path

root = Path.cwd()
sys.path[:0] = [str(root), str(root / 'tests')]
from backend.study_manifest import load_assignment
from backend.study_store import StudyStore
from test_study_store import consent, provenance, event, answer_payload

run_id = 'synthetic-' + uuid.uuid4().hex[:8]
data = root / 'study_data' / run_id
out = root / 'study_exports' / run_id
schedule_path = root / 'study_schedules/cohort-rehearsal-20261019.json'
schedule = json.loads(schedule_path.read_text(encoding='utf-8'))
assignment = load_assignment(schedule_path.parent, schedule['assignments'][0]['assignment_id'], 'olist')
store = StudyStore(data)
aid = store.begin_attempt(assignment, 'synthetic-session', consent(True), provenance())['attempt_id']
for number, kind in enumerate(['trial.ready', 'trial.start', 'trial.task_presented'], 1):
    event(store, aid, number, kind)
store.append_event(aid, 'request.accepted', {'request_id': 'r1', 'classification': 'analytical_request', 'transcript': 'SYNTHETIC_PRIVATE_TRANSCRIPT'}, 100)
artifact = store.enqueue_evidence(aid, {'dashboard_revision': 1, 'views': [], 'filters': []}, {'reason': 'freeze'})
asyncio.run(store.flush_evidence(aid))
event(store, aid, 4, 'trial.freeze', {'reason': 'deadline', 'frozen_revision': 1, 'last_rendered_revision': 1})
event(store, aid, 5, 'trial.answering')
store.apply_event(aid, 'submit', 'answer.submit', answer_payload(evidence_refs=[{'revision': 1, 'artifact_id': artifact}]))
for package in ['technical', 'ratings', 'process']:
    subprocess.run([sys.executable, 'scripts/export_study.py', '--study-data', str(data), '--output', str(out / package), '--package', package], check=True)
ratings = (out / 'ratings/ratings.json').read_text(encoding='utf-8')
assert all(key not in ratings for key in ['condition', 'participant_id', 'session_id', 'transcript', 'created_ns', 'duration'])
assert 'SYNTHETIC_PRIVATE_TRANSCRIPT' in (out / 'process/process.json').read_text(encoding='utf-8')
audit_path = out / 'audit.json'
audit = subprocess.run([sys.executable, 'scripts/audit_study.py', '--schedule', str(schedule_path), '--study-data', str(data), '--output', str(audit_path), '--strict'], check=False)
result = json.loads(audit_path.read_text(encoding='utf-8'))
assert result['planned'] == 12 and result['completed'] == 1 and result['missing'] == 11
assert audit.returncode == 1 and result['diagnostics'], result
print(json.dumps({'synthetic_only': True, 'output': str(out), 'planned': 12, 'completed': 1, 'missing': 11, 'expected_strict_exit': audit.returncode, 'diagnostic_codes': sorted({row['code'] for row in result['diagnostics']})}))
