from backend.render_tracker import RenderTracker


def snapshot(revision=4, views=None):
    return {
        "dashboard_revision": revision,
        "views": views if views is not None else [
            {"id": "view-a", "view_revision": 2},
            {"id": "view-b", "view_revision": 5},
        ],
    }


def rendered(envelope, view_id="view-a", view_revision=2, generation=1, event_id="event-1"):
    return {
        "type": "view.rendered",
        "client_event_id": event_id,
        "render_token": envelope["token"],
        "dashboard_revision": envelope["dashboard_revision"],
        "view_id": view_id,
        "view_revision": view_revision,
        "render_generation": generation,
        "browser_duration_ms": 12.5,
        "presentation": {"mode": "paged", "page_index": 0},
    }


def test_render_tracker_rejects_old_and_forged_ack():
    tracker = RenderTracker()
    old = tracker.register("attempt-a", snapshot(3), "commit")
    current = tracker.register("attempt-a", snapshot(4), "commit")

    assert tracker.ack("attempt-a", rendered(old))["accepted"] is False
    assert tracker.ack("attempt-b", rendered(current))["accepted"] is False
    assert tracker.ack(
        "attempt-a", rendered(current, view_revision=999)
    )["accepted"] is False

    first = tracker.ack("attempt-a", rendered(current))
    assert first == {
        "accepted": True,
        "complete": False,
        "failed": False,
        "dashboard_revision": 4,
        "error_code": None,
    }
    assert tracker.ack("attempt-a", rendered(current)) == first
    assert tracker.ack(
        "attempt-a", rendered(current, "view-b", 5, generation=2, event_id="event-2")
    )["complete"] is True
    assert tracker.status("attempt-a", current["token"])["complete"] is True


def test_frozen_token_independent_of_commit():
    tracker = RenderTracker()
    commit = tracker.register("attempt-a", snapshot(), "commit")
    frozen = tracker.register("attempt-a", snapshot(), "frozen")

    assert commit["token"] != frozen["token"]
    assert commit["expected_views"] == frozen["expected_views"]
    assert tracker.status("attempt-a", commit["token"])["accepted"] is False
    assert tracker.status("attempt-a", frozen["token"])["complete"] is False


def test_empty_dashboard_completes_only_with_explicit_empty_ack():
    tracker = RenderTracker()
    envelope = tracker.register("attempt-empty", snapshot(7, []), "initial")

    assert tracker.status("attempt-empty", envelope["token"])["complete"] is False
    event = rendered(envelope, view_id=None, view_revision=None)
    event["presentation"] = {"mode": "empty", "page_index": None}
    result = tracker.ack("attempt-empty", event)
    assert result["accepted"] is True
    assert result["complete"] is True
    assert tracker.ack("attempt-empty", event) == result

    nonempty = tracker.register("attempt-empty", snapshot(8), "commit")
    forged_empty = rendered(nonempty, view_id=None, view_revision=None)
    forged_empty["presentation"] = {"mode": "empty", "page_index": None}
    assert tracker.ack("attempt-empty", forged_empty)["accepted"] is False


def test_failed_render_marks_token_failed_and_requires_whitelisted_error():
    tracker = RenderTracker()
    envelope = tracker.register("attempt-a", snapshot(), "commit")
    event = rendered(envelope)
    event.update({"type": "view.render_failed", "error_code": "run_async_failed"})

    result = tracker.ack("attempt-a", event)
    assert result == {
        "accepted": True,
        "complete": False,
        "failed": True,
        "dashboard_revision": 4,
        "error_code": "run_async_failed",
    }
    assert tracker.ack("attempt-a", event) == result

    invalid = rendered(envelope, "view-b", 5)
    invalid.update({"type": "view.render_failed", "error_code": "arbitrary details"})
    assert tracker.ack("attempt-a", invalid)["accepted"] is False


def test_client_event_id_is_idempotent_and_conflicts_on_changed_payload():
    tracker = RenderTracker()
    envelope = tracker.register("attempt-a", snapshot(), "commit")
    event = rendered(envelope, event_id="same-id")
    original = tracker.ack("attempt-a", event)
    assert tracker.ack("attempt-a", dict(event)) == original

    changed = dict(event, browser_duration_ms=99)
    conflict = tracker.ack("attempt-a", changed)
    assert conflict["accepted"] is False
    assert conflict["error_code"] == "client_event_conflict"
    assert tracker.ack("attempt-a", rendered(envelope, event_id="bad id"))["accepted"] is False


def test_malformed_types_are_rejected_without_raising():
    tracker = RenderTracker()
    envelope = tracker.register("attempt-a", snapshot(), "commit")
    for change in (
        {"type": ["view.rendered"]},
        {"dashboard_revision": True},
        {"view_revision": True},
        {"view_id": ["view-a"]},
        {"view_revision": {"revision": 2}},
        {"presentation": {"mode": ["paged"], "page_index": 0}},
    ):
        event = rendered(envelope)
        event.update(change)
        assert tracker.ack("attempt-a", event)["accepted"] is False
    bad_error = rendered(envelope)
    bad_error.update({"type":"view.render_failed", "error_code":["run_async_failed"]})
    assert tracker.ack("attempt-a", bad_error)["accepted"] is False


def test_lower_generation_failure_cannot_poison_newer_success():
    tracker = RenderTracker()
    envelope = tracker.register("attempt-a", snapshot(4, [{"id":"view-a", "view_revision":2}]), "commit")
    success = rendered(envelope, generation=3, event_id="newer")
    assert tracker.ack("attempt-a", success)["complete"] is True

    stale = rendered(envelope, generation=2, event_id="older")
    stale.update({"type":"view.render_failed", "error_code":"run_async_failed"})
    rejected = tracker.ack("attempt-a", stale)
    assert rejected["accepted"] is False
    assert tracker.status("attempt-a", envelope["token"])["complete"] is True
    assert tracker.status("attempt-a", envelope["token"])["failed"] is False
