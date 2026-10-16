import json
from pathlib import Path

from scripts.check_study_tools import run_workflows
from test_olist_adapter import olist_csvs  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]


def test_task_pool_has_six_open_ended_tasks():
    payload = json.loads((ROOT / "experiments/olist_study_task_pool.json").read_text(encoding="utf-8"))
    assert payload["status"] == "pilot_pool_not_allocated"
    assert [task["task_id"] for task in payload["tasks"]] == [
        "regional-delivery-risk", "delivery-period-change", "review-delivery-association",
        "freight-definition-robustness", "freight-attribute-association", "seller-delivery-stability"]


def test_six_task_replay_uses_real_toolbox_state(olist_csvs, tmp_path):
    export = tmp_path / "study-views.json"
    events, final = run_workflows(olist_csvs, export=export)
    assert export.exists() and len(json.loads(export.read_text(encoding="utf-8"))) == 6
    assert len(final["views"]) == 7  # six representatives plus the fixed-baseline fork
    assert all(event["elapsed_ms"] >= 0 for event in events)
    assert final["filters"] == []
