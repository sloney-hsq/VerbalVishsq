"""Dataset-independent, process-local authority for analytical effects.

Cancellation is optional. Every effect must still cross the acceptance boundary.
This is not a distributed transaction or a sandbox for untrusted Python tools.
"""
from contextlib import contextmanager
from dataclasses import dataclass, replace
from threading import RLock
from uuid import uuid4


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Response:
    id: str
    epoch: int
    base_revision: int
    authority: str = "active"


@dataclass(frozen=True)
class Batch:
    id: str
    response_id: str
    call_ids: tuple[str, ...]
    state: str = "executing"
    committed_revision: int | None = None


class ResponseProtocol:
    def __init__(self):
        self._lock = RLock()
        self._epoch = 0
        self._current = None
        self._responses: dict[str, Response] = {}
        self._batches: dict[str, Batch] = {}
        self._deliveries: set[tuple[str, str]] = set()

    @property
    def epoch(self):
        with self._lock:
            return self._epoch

    @property
    def current(self):
        with self._lock:
            return self._responses.get(self._current)

    @contextmanager
    def guard(self):
        """Held across local authorization and Store installation; never await."""
        with self._lock:
            yield

    def begin_response(self, base_revision: int) -> Response:
        if type(base_revision) is not int or base_revision < 0:
            raise ProtocolError("invalid base revision")
        with self._lock:
            self._revoke_current()
            response = Response(uuid4().hex, self._epoch, base_revision)
            self._responses[response.id] = response
            self._current = response.id
            self._prune()
            return response

    def _revoke_current(self):
        if self._current in self._responses:
            r = self._responses[self._current]
            self._responses[r.id] = replace(r, authority="revoked")

    def revise(self):
        with self._lock:
            self._revoke_current()
            self._current = None
            self._epoch += 1
            return self._epoch

    def revoke(self, response_id):
        with self._lock:
            if response_id in self._responses:
                r = self._responses[response_id]
                self._responses[r.id] = replace(r, authority="revoked")

    def suspend(self):
        with self._lock:
            r = self.current
            if r and r.authority == "active":
                self._responses[r.id] = replace(r, authority="suspended")

    def resume(self):
        with self._lock:
            r = self.current
            if r and r.authority == "suspended":
                self._responses[r.id] = replace(r, authority="active")

    def allowed(self, response_id) -> bool:
        with self._lock:
            r = self._responses.get(response_id)
            return bool(r and r.id == self._current and r.epoch == self._epoch
                        and r.authority == "active")

    def admit(self, response_id, call_ids) -> Batch:
        with self._lock:
            if not self.allowed(response_id):
                raise ProtocolError("response has no execution authority")
            ids = tuple(call_ids)
            if not ids or any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
                raise ProtocolError("empty or duplicate call IDs")
            if any(b.response_id == response_id for b in self._batches.values()):
                raise ProtocolError("response batch already admitted")
            batch = Batch(uuid4().hex, response_id, ids)
            self._batches[batch.id] = batch
            return batch

    def batch(self, batch_id):
        with self._lock:
            return self._batches.get(batch_id)

    def finish_batch(self, batch_id, success):
        with self._lock:
            b = self._batches.get(batch_id)
            if b and b.state == "executing":
                self._batches[b.id] = replace(b, state="succeeded" if success else "failed")

    def authorize_commit(self, batch_id, current_revision):
        with self._lock:
            b = self._batches.get(batch_id)
            r = self._responses.get(b.response_id) if b else None
            return bool(b and r and b.state == "succeeded" and self.allowed(r.id)
                        and r.base_revision == current_revision)

    def record_commit(self, batch_id, revision):
        with self._lock:
            b = self._batches.get(batch_id)
            r = self._responses.get(b.response_id) if b else None
            if not b or not r or b.state != "succeeded" or not self.allowed(r.id):
                raise ProtocolError("cannot record unauthorized commit")
            if type(revision) is not int or revision not in (r.base_revision, r.base_revision + 1):
                raise ProtocolError("invalid installation revision")
            self._batches[b.id] = replace(b, state="committed", committed_revision=revision)

    def allow_output(self, response_id, batch_id=None):
        with self._lock:
            if not self.allowed(response_id):
                return False
            if batch_id is None:
                return True
            b = self._batches.get(batch_id)
            return bool(b and b.response_id == response_id and b.state == "committed")

    def consume_output(self, response_id, batch_id, key, *, error=False):
        """Linearize a send permit; remote delivery can occur after revocation."""
        with self._lock:
            b = self._batches.get(batch_id)
            valid = bool(b and b.response_id == response_id and self.allowed(response_id)
                         and b.state == ("failed" if error else "committed"))
            token = (batch_id, key)
            if not valid or token in self._deliveries:
                return False
            self._deliveries.add(token)
            return True

    def _prune(self):
        # Old callbacks become unknown/denied, never regain authority.
        while len(self._responses) > 256:
            old = next(iter(self._responses))
            del self._responses[old]
            batch_ids = {k for k, v in self._batches.items() if v.response_id == old}
            for k in batch_ids:
                del self._batches[k]
            self._deliveries = {x for x in self._deliveries if x[0] not in batch_ids}
