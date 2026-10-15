import json

import pytest

from scripts.analyze_traces import analyze_jsonl, main


def record(seq, event, *, session="s1", mono=None, data=None, correlation=None,
           trial="t1", condition="revision_enabled", **extra):
    row = {
        "schema_version": 2,
        "seq": seq,
        "session_id": session,
        "participant_id": "p1",
        "trial_id": trial,
        "task_id": "task1",
        "dataset_id": "olist",
        "condition": condition,
        "observed_at": "2026-01-01T00:00:00+00:00",
        "monotonic_ns": seq * 1_000_000 if mono is None else mono,
        "event": event,
        "correlation": correlation or {},
        "data": data or {},
    }
    row.update(extra)
    return row


def line(row):
    return json.dumps(row, separators=(",", ":"), ensure_ascii=False)


def trial(result, session="s1"):
    return next(item for item in result["trials"] if item["session_id"] == session)


def test_complete_no_tool_trial_uses_explicit_request_settlement():
    rows = [
        record(1, "session.started", mono=100),
        record(2, "user.request_received", mono=200, correlation={"request_id": "r1"},
               data={"received_at_monotonic_ns": 200}),
        record(3, "response.finished", mono=500, correlation={"request_id": "r1", "response_id": "x1"}),
        record(4, "request.settled", mono=900, correlation={"request_id": "r1"}),
        record(5, "session.closed", mono=1_100),
    ]
    result = analyze_jsonl("\n".join(map(line, rows)), source_name="trace.jsonl")
    item = trial(result)
    assert item["request_count"] == 1
    assert item["duration_ms"] == 0.001
    assert item["duration_complete"] is True
    assert item["time_to_final_state_ms"] == 0.0007
    assert item["revision_saving_window_ms"] is None


def test_followup_responses_and_duplicate_semantic_request_count_once():
    rows = [record(1, "session.started")]
    rows += [record(2, "user.request_received", correlation={"request_id": "r1"},
                    data={"received_at_monotonic_ns": 2_000_000})]
    rows += [record(3, "response.finished", correlation={"request_id": "r1", "response_id": "x1"}),
             record(4, "response.finished", correlation={"request_id": "r1", "response_id": "x2"}),
             record(5, "user.request_received", correlation={"request_id": "r1"},
                    data={"received_at_monotonic_ns": 2_000_000}),
             record(6, "request.settled", correlation={"request_id": "r1"}),
             record(7, "session.closed")]
    result = analyze_jsonl("\n".join(map(line, rows)))
    item = trial(result)
    assert item["request_count"] == 1
    assert any(d["code"] == "duplicate_semantic_event" for d in item["diagnostics"])


def test_revision_count_and_saving_window_require_observed_previous_settlement():
    rows = [record(1, "session.started"),
            record(2, "user.request_received", mono=2_000_000,
                   correlation={"request_id": "r1"}, data={"received_at_monotonic_ns": 2_000_000}),
            record(3, "request.settled", mono=5_000_000, correlation={"request_id": "r1"}),
            record(4, "user.request_received", mono=6_000_000,
                   correlation={"request_id": "r2"}, data={"received_at_monotonic_ns": 6_000_000}),
            record(5, "user.request_received", mono=6_050_000,
                   correlation={"request_id": "r3"}, data={"received_at_monotonic_ns": 6_050_000}),
            record(6, "revision.received", mono=6_100_000,
                   correlation={"request_id": "r3", "previous_request_id": "r2"},
                   data={"in_flight": True, "received_at_monotonic_ns": 6_100_000}),
            record(7, "request.settled", mono=7_000_000, correlation={"request_id": "r3"}),
            record(8, "session.closed", mono=8_000_000)]
    result = analyze_jsonl("\n".join(map(line, rows)))
    item = trial(result)
    assert item["request_count"] == 3
    assert item["in_flight_revision_count"] == 1
    # r2 was not observed settled; r1's unrelated settlement is not a substitute.
    assert item["revision_saving_window_ms"] is None


def test_settled_request_followed_by_ordinary_request_is_not_an_in_flight_revision():
    rows = [record(1, "session.started"),
            record(2, "user.request_received", mono=2_000_000,
                   correlation={"request_id": "r1"}, data={"received_at_monotonic_ns": 2_000_000}),
            record(3, "request.settled", mono=3_000_000, correlation={"request_id": "r1"}),
            record(4, "user.request_received", mono=4_000_000,
                   correlation={"request_id": "r2"}, data={"received_at_monotonic_ns": 4_000_000}),
            record(5, "request.settled", mono=6_000_000, correlation={"request_id": "r2"}),
            record(6, "session.closed", mono=7_000_000)]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["request_count"] == 2
    assert item["in_flight_revision_count"] == 0
    assert item["time_to_final_state_ms"] == 2.0


def test_request_count_fallback_is_used_only_without_canonical_receive_events():
    rows = [record(1, "session.started"),
            record(2, "request.received", correlation={"request_id": "r1"},
                   data={"received_at_monotonic_ns": 2_000_000}),
            record(3, "revision.received", correlation={"request_id": "r2", "previous_request_id": "r1"},
                   data={"in_flight": True, "received_at_monotonic_ns": 3_000_000}),
            record(4, "session.closed")]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["request_count"] == 2
    assert any(d["code"] == "request_count_fallback" for d in item["diagnostics"])


def test_partial_canonical_receives_use_fallback_only_for_missing_request_ids():
    rows = [record(1, "session.started"),
            record(2, "user.request_received", correlation={"request_id": "r1"},
                   data={"received_at_monotonic_ns": 2_000_000}),
            record(3, "revision.received", correlation={"request_id": "r1", "previous_request_id": "r0"},
                   data={"in_flight": True, "received_at_monotonic_ns": 3_000_000}),
            record(4, "request.received", correlation={"request_id": "r2"},
                   data={"received_at_monotonic_ns": 4_000_000}),
            record(5, "session.closed")]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["request_count"] == 2
    assert any(d["code"] == "request_count_fallback" for d in item["diagnostics"])


@pytest.mark.parametrize("commit_status, expected", [
    ("committed", 0), ("read_only", 0), ("no_change", 0), ("failed", 0),
    ("conflicted", 0), ("superseded", 1),
])
def test_batch_outcomes_count_only_superseded_batches_and_calls(commit_status, expected):
    execution_status = "failed" if commit_status == "failed" else "succeeded"
    rows = [record(1, "session.started"),
            record(2, "batch.outcome", correlation={"batch_id": "b1", "request_id": "r1"},
                   data={"execution_status": execution_status, "commit_status": commit_status,
                         "state_changed": commit_status == "committed", "call_ids": ["c1", "c2"]}),
            record(3, "session.closed")]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["superseded_batch_count"] == expected
    assert item["superseded_call_count"] == expected * 2


def test_superseded_call_count_uses_batch_and_call_id_as_identity():
    rows = [record(1, "session.started")]
    for seq, batch_id, call_ids in [(2, "b1", ["c1", "c2", "c1"]), (3, "b2", ["c1"])]:
        rows.append(record(seq, "batch.outcome", correlation={"batch_id": batch_id},
                           data={"execution_status": "succeeded", "commit_status": "superseded",
                                 "state_changed": False, "call_ids": call_ids}))
    rows.append(record(4, "session.closed"))
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["superseded_batch_count"] == 2
    assert item["superseded_call_count"] == 3


def test_invalid_batch_outcome_is_diagnosed_and_excluded():
    rows = [record(1, "session.started"),
            record(2, "batch.outcome", correlation={"batch_id": "b1"},
                   data={"execution_status": "succeeded", "commit_status": "committed",
                         "state_changed": False, "call_ids": ["c1"]}),
            record(3, "session.closed")]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["superseded_batch_count"] == 0
    assert any(d["code"] == "invalid_batch_outcome" for d in item["diagnostics"])


def test_unhashable_status_and_phase_fields_are_diagnostics_not_crashes():
    rows = [record(1, "session.started"),
            record(2, "request.phase_changed", correlation={"request_id": "r1"},
                   data={"to_phase": ["settled"]}),
            record(3, "batch.outcome", correlation={"batch_id": "b1"},
                   data={"execution_status": [], "commit_status": [], "state_changed": False, "call_ids": []}),
            record(4, "session.closed")]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert any(d["code"] == "invalid_batch_outcome" for d in item["diagnostics"])
    assert item["time_to_final_state_ms"] is None


def test_only_real_batch_dashboard_committed_events_count():
    rows = [record(1, "session.started"),
            record(2, "dashboard.committed", correlation={"batch_id": "b1"}),
            record(3, "dashboard.committed", correlation={"batch_id": "b1"}),
            record(4, "dashboard.committed"),
            record(5, "batch.outcome", correlation={"batch_id": "b2"},
                   data={"execution_status": "succeeded", "commit_status": "committed",
                         "state_changed": True, "call_ids": ["c2"]}),
            record(6, "session.closed")]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["dashboard_commit_count"] == 1


def test_saving_window_uses_only_exact_observed_previous_request_settlement():
    rows = [record(1, "session.started"),
            record(2, "user.request_received", mono=1_000_000,
                   correlation={"request_id": "r1"}, data={"received_at_monotonic_ns": 1_000_000}),
            record(3, "revision.received", mono=2_000_000,
                   correlation={"request_id": "r2", "previous_request_id": "r1"},
                   data={"in_flight": True, "received_at_monotonic_ns": 2_000_000}),
            record(4, "request.settled", mono=6_000_000, correlation={"request_id": "r1"}),
            record(5, "request.settled", mono=8_000_000, correlation={"request_id": "r2"}),
            record(6, "session.closed", mono=9_000_000)]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["revision_saving_window_ms"] == 4.0


@pytest.mark.parametrize("old_terminal", ["response.done", "request.failed", "response.superseded"])
def test_unsettled_or_unrelated_old_terminal_never_becomes_saving_window(old_terminal):
    rows = [record(1, "session.started"),
            record(2, "user.request_received", mono=1_000_000,
                   correlation={"request_id": "old"}, data={"received_at_monotonic_ns": 1_000_000}),
            record(3, old_terminal, mono=3_000_000,
                   correlation={"request_id": "other" if old_terminal == "request.failed" else "old"}),
            record(4, "revision.received", mono=4_000_000,
                   correlation={"request_id": "new", "previous_request_id": "old"},
                   data={"in_flight": True, "received_at_monotonic_ns": 4_000_000}),
            record(5, "session.closed", mono=5_000_000)]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["revision_saving_window_ms"] is None


def test_multiple_revisions_keep_per_revision_values_but_no_ambiguous_scalar():
    rows = [record(1, "session.started"),
            record(2, "user.request_received", mono=1_000_000,
                   correlation={"request_id": "old1"}, data={"received_at_monotonic_ns": 1_000_000}),
            record(3, "request.settled", mono=2_000_000, correlation={"request_id": "old1"}),
            record(4, "revision.received", mono=3_000_000,
                   correlation={"request_id": "new1", "previous_request_id": "old1"},
                   data={"in_flight": True, "received_at_monotonic_ns": 3_000_000}),
            record(5, "revision.received", mono=4_000_000,
                   correlation={"request_id": "new2", "previous_request_id": "new1"},
                   data={"in_flight": True, "received_at_monotonic_ns": 4_000_000}),
            record(6, "session.closed", mono=5_000_000)]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["revision_saving_windows_ms"] == [None, None]
    assert item["revision_saving_window_ms"] is None


def test_negative_saving_window_is_diagnosed_and_null():
    rows = [record(1, "session.started"),
            record(2, "request.settled", mono=1_000_000, correlation={"request_id": "r1"}),
            record(3, "revision.received", mono=2_000_000,
                   correlation={"request_id": "r2", "previous_request_id": "r1"},
                   data={"in_flight": True, "received_at_monotonic_ns": 2_000_000}),
            record(4, "session.closed", mono=3_000_000)]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["revision_saving_window_ms"] is None
    assert any(d["code"] == "negative_saving_window" for d in item["diagnostics"])


def test_revision_missing_previous_id_or_receive_time_is_diagnosed_and_null():
    rows = [record(1, "session.started"),
            record(2, "revision.received", correlation={"request_id": "r2"},
                   data={"in_flight": True}),
            record(3, "session.closed")]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["in_flight_revision_count"] == 1
    assert item["revision_saving_window_ms"] is None
    codes = {d["code"] for d in item["diagnostics"]}
    assert {"missing_previous_request_id", "missing_revision_timestamp"} <= codes


def test_revision_received_with_false_in_flight_flag_is_diagnosed_not_counted():
    rows = [record(1, "session.started"),
            record(2, "revision.received", correlation={"request_id": "r2", "previous_request_id": "r1"},
                   data={"in_flight": False, "received_at_monotonic_ns": 2_000_000}),
            record(3, "session.closed")]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["in_flight_revision_count"] == 0
    assert any(d["code"] == "invalid_revision_flag" for d in item["diagnostics"])


def test_multiple_sessions_with_same_trial_id_keep_monotonic_clocks_separate():
    rows = [record(1, "session.started", session="s1", mono=100),
            record(2, "session.closed", session="s1", mono=200),
            record(1, "session.started", session="s2", mono=9_000_000_000, trial="t1"),
            record(2, "session.closed", session="s2", mono=9_001_000_000, trial="t1")]
    result = analyze_jsonl("\n".join(map(line, rows)))
    assert [item["session_id"] for item in result["trials"]] == ["s1", "s2"]
    assert [item["duration_ms"] for item in result["trials"]] == [0.0001, 1.0]


def test_physical_reordering_gaps_exact_duplicates_and_conflicting_seq_are_diagnosed():
    first = record(1, "session.started", mono=100)
    close = record(3, "session.closed", mono=300)
    content = "\n".join([line(close), line(first), line(first),
                         line(record(3, "session.closed", mono=301))])
    result = analyze_jsonl(content)
    item = trial(result)
    codes = {d["code"] for d in item["diagnostics"]}
    assert "physical_reordering" in codes
    assert "duplicate_record" in codes
    assert "sequence_conflict" in codes
    assert "sequence_gap" in codes
    assert item["duration_ms"] == 0.0002  # first physical seq=3 wins


def test_sequence_starting_after_one_is_reported_as_a_gap():
    rows = [record(4, "session.started"), record(5, "session.closed")]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert any(d["code"] == "sequence_gap" for d in item["diagnostics"])


def test_malformed_truncated_v1_unknown_and_valid_no_newline_are_recovered():
    rows = [record(1, "session.started"), record(2, "future.event"), record(3, "session.closed")]
    content = "\n".join([line(rows[0]), "{bad-json", line({**rows[1], "schema_version": 1}),
                          line(rows[1]), line(rows[2])])  # final line deliberately lacks newline
    result = analyze_jsonl(content)
    item = trial(result)
    codes = {d["code"] for d in result["diagnostics"]}
    codes |= {d["code"] for d in item["diagnostics"]}
    assert {"malformed_json", "unsupported_schema", "unknown_event"} <= codes
    assert item["duration_complete"] is True


def test_truncated_final_line_without_newline_is_diagnosed():
    content = line(record(1, "session.started")) + "\n" + '{"schema_version":2,"seq":2'
    result = analyze_jsonl(content)
    assert any(row["code"] == "malformed_json" for row in result["diagnostics"])


def test_overdeep_json_line_is_diagnosed_without_crashing():
    result = analyze_jsonl("[" * 20000 + "0" + "]" * 20000)
    assert result["summary"]["diagnostic_count"] == 1
    assert result["diagnostics"][0]["code"] == "malformed_json"


def test_bad_fields_missing_lifecycle_and_private_content_are_not_emitted():
    private = "CONSENTED PRIVATE TRANSCRIPT"
    rows = [record(1, "session.started", transcript=private),
            record(True, "ignored.bad", correlation={"request_id": "invalid"}),
            record(2, "user.request_received", correlation={"request_id": "r1"},
                   data={"received_at_monotonic_ns": True, "transcript": private}),
            record(3, "session.closed", data={"arguments": private})]
    result = analyze_jsonl("\n".join(map(line, rows)))
    item = trial(result)
    encoded = json.dumps(item)
    assert private not in encoded
    assert "transcript" not in encoded and "arguments" not in encoded
    assert any(d["code"] == "missing_request_terminal" for d in item["diagnostics"])
    assert any(d["code"] == "missing_request_timestamp" for d in item["diagnostics"])
    assert any(d["code"] == "invalid_seq" for d in result["diagnostics"])
    assert item["request_count"] == 1


def test_context_conflict_excludes_conflicting_record():
    rows = [record(1, "session.started"),
            record(2, "user.request_received", trial="other", correlation={"request_id": "r1"},
                   data={"received_at_monotonic_ns": 2_000_000}),
            record(3, "session.closed")]
    result = analyze_jsonl("\n".join(map(line, rows)))
    item = trial(result)
    assert item["request_count"] == 0
    assert any(d["code"] == "context_conflict" for d in item["diagnostics"])


def test_missing_close_uses_last_observed_lower_bound_and_missing_start_is_null():
    rows = [record(2, "response.finished", mono=2_000_000, session="no-start"),
            record(3, "response.finished", mono=3_000_000, session="no-start"),
            record(1, "session.started", mono=10, session="no-close"),
            record(2, "response.finished", mono=1_000_010, session="no-close")]
    result = analyze_jsonl("\n".join(map(line, rows)))
    no_close = trial(result, "no-close")
    no_start = trial(result, "no-start")
    assert no_close["duration_ms"] == 1.0
    assert no_close["duration_complete"] is False
    assert no_start["duration_ms"] is None
    assert no_start["duration_complete"] is False


def test_missing_close_lower_bound_includes_valid_unknown_events():
    rows = [record(1, "session.started", mono=10),
            record(2, "future.event", mono=1_000_010)]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["duration_ms"] == 1.0
    assert item["duration_complete"] is False


def test_invalid_schema_context_and_timing_records_are_diagnosed_and_excluded():
    rows = [record(1, "session.started"),
            {**record(2, "user.request_received", correlation={"request_id": "r1"}), "condition": "half_duplex"},
            {**record(3, "request.settled"), "monotonic_ns": True},
            record(4, "session.closed")]
    result = analyze_jsonl("\n".join(map(line, rows)))
    item = trial(result)
    codes = {row["code"] for row in result["diagnostics"]}
    assert "invalid_context" in codes
    assert "invalid_monotonic_ns" in codes
    assert item["request_count"] == 0


def test_unhashable_condition_is_rejected_as_invalid_context():
    rows = [record(1, "session.started"),
            {**record(2, "session.closed"), "condition": ["revision_enabled"]}]
    result = analyze_jsonl("\n".join(map(line, rows)))
    item = trial(result)
    assert item["duration_complete"] is False
    assert any(d["code"] == "invalid_context" for d in result["diagnostics"])


def test_extremely_large_timing_values_do_not_crash_or_emit_infinity():
    huge = 10 ** 1000
    rows = [record(1, "session.started", mono=huge),
            record(2, "session.closed", mono=huge * 2)]
    item = trial(analyze_jsonl("\n".join(map(line, rows))))
    assert item["duration_ms"] is None
    assert math_is_finite_json(json.dumps(item))
    assert any(d["code"] == "timing_overflow" for d in item["diagnostics"])


def math_is_finite_json(value):
    return "Infinity" not in value and "NaN" not in value


def test_no_consent_redactions_and_unknown_payload_are_not_echoed():
    private = "TRANSCRIPT SHOULD NEVER LEAK"
    rows = [record(1, "session.started", data={"transcript": "[redacted]", "payload": private}),
            record(2, "session.closed")]
    result = analyze_jsonl("\n".join(map(line, rows)))
    rendered = json.dumps(result)
    assert private not in rendered
    assert "transcript" not in rendered and "payload" not in rendered


def test_analyzer_output_is_byte_deterministic_and_has_no_monotonic_baseline():
    from scripts.analyze_traces import _render

    rows = [record(1, "session.started", mono=123456789), record(2, "session.closed", mono=223456789)]
    text = "\n".join(map(line, rows))
    a = _render(analyze_jsonl(text, source_name="private/path/trace.jsonl"))
    b = _render(analyze_jsonl(text, source_name="private/path/trace.jsonl"))
    assert a == b
    assert "123456789" not in a and "private/path" not in a
    assert analyze_jsonl(text)["source"] == "trace.jsonl"


def test_streaming_line_api_matches_text_api():
    from scripts.analyze_traces import analyze_lines

    rows = [record(1, "session.started"), record(2, "session.closed")]
    text = "\n".join(map(line, rows))
    assert analyze_lines(iter(text.splitlines())) == analyze_jsonl(text)


def test_cli_stdout_output_and_strict_exit_behavior(tmp_path, capsys):
    input_path = tmp_path / "trace.jsonl"
    input_path.write_text("{bad}\n", encoding="utf-8")
    assert main([str(input_path)]) == 0
    stdout_result = json.loads(capsys.readouterr().out)
    assert stdout_result["summary"]["diagnostic_count"] > 0
    output_path = tmp_path / "summary.json"
    assert main([str(input_path), "--output", str(output_path), "--strict"]) == 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["schema_version"] == 1
    with pytest.raises(SystemExit):
        main([str(tmp_path / "missing.jsonl")])


def test_cli_output_write_error_is_nonzero(tmp_path):
    input_path = tmp_path / "good.jsonl"
    input_path.write_text(line(record(1, "session.started")) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        main([str(input_path), "--output", str(tmp_path / "missing" / "report.json")])


def test_cli_refuses_to_overwrite_input_trace(tmp_path):
    input_path = tmp_path / "trace.jsonl"
    input_path.write_text(line(record(1, "session.started")), encoding="utf-8")
    original = input_path.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        main([str(input_path), "--output", str(input_path)])
    assert input_path.read_text(encoding="utf-8") == original


def test_checked_in_cli_fixture_has_expected_summary():
    from pathlib import Path
    from scripts.analyze_traces import analyze_path

    source = Path(__file__).parent / "fixtures" / "trace_v2_analyzer.jsonl"
    item = trial(analyze_path(source), "demo-session")
    assert item["request_count"] == 2
    assert item["dashboard_commit_count"] == 1
    assert item["duration_ms"] == 1_000.0
    assert item["time_to_final_state_ms"] == 100.0
