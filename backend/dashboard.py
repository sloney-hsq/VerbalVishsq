"""Private dashboard drafts with compare-and-swap commit and staged undo."""
from copy import deepcopy
from dataclasses import dataclass
import threading


@dataclass(eq=False)
class Draft:
    document: dict
    base_revision: int
    dirty: bool = False


class Dashboard:
    def __init__(self, dataset_id: str, dataset_version: str):
        if not all(isinstance(v, str) and v for v in (dataset_id, dataset_version)):
            raise ValueError('Dataset identity and version are required')
        self._lock = threading.RLock()
        self._document = {'views': [], 'filters': [], 'highlighted': [],
                          'highlight_element': None, 'dim_others': False,
                          'active_view_id': None,
                          'dashboard_revision': 0, 'dataset_id': dataset_id,
                          'dataset_version': dataset_version}
        self._drafts = {}
        self._history = []

    def snapshot(self):
        with self._lock:
            return deepcopy(self._document)

    def begin_draft(self):
        with self._lock:
            draft = Draft(deepcopy(self._document), self._document['dashboard_revision'])
            self._drafts[id(draft)] = {'draft': draft, 'base': draft.base_revision,
                                       'original': deepcopy(draft.document), 'undo': None}
            return draft

    def _record(self, draft):
        record = self._drafts.get(id(draft))
        if record is None or record['draft'] is not draft:
            raise ValueError('Draft is foreign, discarded, or already committed')
        if type(draft.base_revision) is not int or draft.base_revision != record['base']:
            raise ValueError('Draft base revision was modified')
        return record

    def validate_draft(self, draft, *, mutation=False):
        """Validate ownership; stale drafts may execute but can never commit."""
        with self._lock:
            record = self._record(draft)
            if mutation and record['undo'] is not None:
                raise ValueError('Undo must be a standalone mutation')

    def stage_undo(self, draft):
        with self._lock:
            record = self._record(draft)
            if draft.dirty or draft.document != record['original'] or record['undo'] is not None:
                raise ValueError('Undo must be a standalone mutation')
            if record['base'] != self._document['dashboard_revision']:
                raise ValueError('Dashboard revision conflict')
            if not self._history:
                raise ValueError('No committed dashboard change to undo')
            target = deepcopy(self._history[-1])
            existing = {view['id'] for view in target['views']}
            target['active_view_id'] = target.get('active_view_id') if target.get('active_view_id') in existing else None
            target['highlighted'] = [view_id for view_id in target['highlighted'] if view_id in existing]
            if not target['highlighted']:
                target['highlight_element'] = None
            target['dashboard_revision'] = record['base']
            record['undo'] = deepcopy(target)
            draft.document = target
            draft.dirty = True

    def commit(self, draft):
        with self._lock:
            record = self._record(draft)
            if record['base'] != self._document['dashboard_revision']:
                raise ValueError('Dashboard revision conflict')
            candidate = deepcopy(draft.document)
            for key in ('dataset_id', 'dataset_version', 'dashboard_revision'):
                if candidate.get(key) != self._document[key]:
                    raise ValueError('Draft identity or revision was modified')
            if record['undo'] is not None and candidate != record['undo']:
                raise ValueError('Staged undo was modified')
            changed = candidate != self._document
            if changed and not draft.dirty:
                raise ValueError('Changed draft must be marked dirty')
            if changed:
                if record['undo'] is not None:
                    self._history.pop()
                else:
                    analytic_keys = ('views', 'filters')
                    old_analysis = tuple([{k: v for k, v in view.items() if k not in {'highlighted', 'selection_highlights'}} for view in self._document[key]]
                                         if key == 'views' else self._document[key] for key in analytic_keys)
                    new_analysis = tuple([{k: v for k, v in view.items() if k not in {'highlighted', 'selection_highlights'}} for view in candidate[key]]
                                         if key == 'views' else candidate[key] for key in analytic_keys)
                    if old_analysis != new_analysis:
                        self._history.append(deepcopy(self._document))
                candidate['dashboard_revision'] += 1
                self._document = candidate
            del self._drafts[id(draft)]
            return deepcopy(self._document)

    def discard(self, draft):
        """Idempotent cleanup, including after a successful commit."""
        with self._lock:
            record = self._drafts.get(id(draft))
            if record is not None and record['draft'] is draft:
                del self._drafts[id(draft)]
