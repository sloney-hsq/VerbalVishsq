"""Validate displayed marks and translate selectable dimensions to source filters."""
from datetime import date, timedelta


_OPERATORS = {'eq', 'neq', 'gte', 'gt', 'lte', 'lt'}
_BIN_START = {'bin_start': 'bin_end', 'x_bin_start': 'x_bin_end', 'y_bin_start': 'y_bin_end'}


def _matches(value, op, selected):
    if op == 'eq':
        return value == selected
    if op == 'neq':
        return value != selected
    if value is None or selected is None:
        return False
    return {'gte': lambda: value >= selected, 'gt': lambda: value > selected,
            'lte': lambda: value <= selected, 'lt': lambda: value < selected}[op]()


def match_predicate(view, predicate, *, require_raw=False):
    if not predicate:
        raise ValueError('INVALID_SELECTION: predicate is required')
    columns, encoding = view['columns'], view['visual']['encoding']
    selected = []
    for item in predicate:
        field = encoding.get(item['field'], item['field'])
        entry = columns.get(field)
        if (not entry or item['op'] not in _OPERATORS or 'value' not in item or
                field not in encoding.values() and field not in _BIN_START and field not in _BIN_START.values()):
            raise ValueError('INVALID_SELECTION: predicate field or operator is not displayed')
        if require_raw and not entry.get('source_field'):
            raise ValueError('INVALID_SELECTION: derived measure is not a row predicate')
        selected.append((field, item, entry.get('source_field')))
    matches = [row for row in view['data'] if all(_matches(row.get(field), item['op'], item['value']) for field, item, _ in selected)]
    if not matches:
        raise ValueError('INVALID_SELECTION: no displayed mark matches predicate')
    return selected, matches


def selection_filters(view, predicate):
    selected, matches = match_predicate(view, predicate, require_raw=True)
    raw = []
    for field, item, source in selected:
        entry = view['columns'][field]
        if entry.get('time_bucket'):
            if item['op'] != 'eq':
                raise ValueError('INVALID_SELECTION: time bucket selection requires equality')
            start = date.fromisoformat(str(item['value'])[:10])
            bucket = entry['time_bucket']
            if bucket == 'week':
                end = start + timedelta(days=7)
            else:
                month = start.month + (3 if bucket == 'quarter' else 1)
                end = date(start.year + (month - 1) // 12, (month - 1) % 12 + 1, 1)
            raw.extend([{'field': source, 'op': 'gte', 'value': start.isoformat()},
                        {'field': source, 'op': 'lt', 'value': end.isoformat()}])
        elif field in _BIN_START:
            if item['op'] != 'eq':
                raise ValueError('INVALID_SELECTION: bin selection requires equality')
            end_field = _BIN_START[field]
            endings = {row.get(end_field) for row in matches}
            if len(endings) != 1:
                raise ValueError('INVALID_SELECTION: ambiguous bin selection')
            upper = next(iter(endings))
            if field == 'bin_start':
                last = view.get('metadata', {}).get('bin_edges', [None])[-1]
            else:
                axis = 'x' if field.startswith('x_') else 'y'
                last = view.get('metadata', {}).get('bins', {}).get(axis + '_edges', [None])[-1]
            raw.extend([{'field': source, 'op': 'gte', 'value': item['value']},
                        {'field': source, 'op': 'lte' if upper == last else 'lt', 'value': upper}])
        elif field not in _BIN_START.values():
            raw.append({'field': source, 'op': item['op'], 'value': item['value']})
    return raw
