import pytest

from refactor_next.backend.response_protocol import ResponseProtocol, ProtocolError


def test_revocation_rejects_late_commit_even_after_successful_execution():
    p = ResponseProtocol()
    r = p.begin_response(0)
    b = p.admit(r.id, ["call-1"])
    p.revise()
    p.finish_batch(b.id, True)
    assert not p.authorize_commit(b.id, 0)
    assert not p.allowed(r.id)
    assert not p.allow_output(r.id, b.id)


def test_success_requires_current_revision_and_commits_only_once():
    p = ResponseProtocol()
    r = p.begin_response(4)
    b = p.admit(r.id, ["c"])
    assert not p.authorize_commit(b.id, 4)
    p.finish_batch(b.id, True)
    assert not p.authorize_commit(b.id, 5)
    assert p.authorize_commit(b.id, 4)
    p.record_commit(b.id, 5)
    assert p.allow_output(r.id, b.id)
    assert not p.authorize_commit(b.id, 5)
    p.revise()
    assert p.batch(b.id).state == "committed"
    assert not p.allow_output(r.id, b.id)


def test_duplicate_calls_are_not_admitted_and_unknown_response_has_no_authority():
    p = ResponseProtocol()
    r = p.begin_response(0)
    with pytest.raises(ProtocolError):
        p.admit(r.id, ["same", "same"])
    p.admit(r.id, ["same"])
    with pytest.raises(ProtocolError):
        p.admit(r.id, ["same"])
    assert not p.allowed("provider-created-id")


def test_suspension_does_not_advance_epoch_and_cannot_revive_revoked_response():
    p = ResponseProtocol()
    r = p.begin_response(0)
    p.suspend()
    assert p.epoch == 0
    assert not p.allowed(r.id)
    p.resume()
    assert p.allowed(r.id)
    p.revise()
    p.resume()
    assert not p.allowed(r.id)


def test_readonly_commit_keeps_revision_and_followup_stays_in_same_epoch():
    p = ResponseProtocol()
    r = p.begin_response(2)
    b = p.admit(r.id, ["read"])
    p.finish_batch(b.id, True)
    p.record_commit(b.id, 2)
    assert p.allow_output(r.id, b.id)
    new = p.begin_response(2)
    assert new.epoch == r.epoch
    assert not p.allowed(r.id)


def test_finish_failure_cannot_be_promoted_to_success():
    p = ResponseProtocol()
    r = p.begin_response(0)
    b = p.admit(r.id, ["bad"])
    p.finish_batch(b.id, False)
    p.finish_batch(b.id, True)
    assert not p.authorize_commit(b.id, 0)
    with pytest.raises(ProtocolError):
        p.record_commit(b.id, 1)
