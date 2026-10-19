"""Bounded provider projections, separate from authoritative schemas and evidence."""
from copy import deepcopy
import json
from .view_references import chart_display_numbers


MAX_PROVIDER_BYTES = 256 * 1024


class ProviderMessageTooLarge(ValueError):
    def __init__(self, event_type, size):
        self.event_type, self.size = event_type, size
        super().__init__(f'provider_message_too_large: {event_type} is {size} bytes; '
                         f'limit is {MAX_PROVIDER_BYTES}. Narrow the requested scope.')


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def encode_provider_event(event):
    encoded = compact_json(event)
    size = len(encoded.encode('utf-8'))
    if size > MAX_PROVIDER_BYTES:
        raise ProviderMessageTooLarge(event.get('type', 'unknown'), size)
    return encoded


def model_tool_definitions(definitions):
    """Keep domain schemas once, replacing only exact nested source copies.

    The full schemas remain the execution validators. A source's arguments use
    the schema of its named registered tool, also sent in the same session.
    """
    parameters = {d['name']: d.get('parameters') for d in definitions}

    def project(node):
        if isinstance(node, list):
            return [project(v) for v in node]
        if not isinstance(node, dict):
            return node
        branches = node.get('oneOf')
        names = []
        if set(node) == {'oneOf'} and isinstance(branches, list) and branches:
            for branch in branches:
                if not isinstance(branch, dict):
                    break
                props = branch.get('properties', {})
                tool_schema = props.get('tool', {})
                if not isinstance(tool_schema, dict):
                    break
                tool = tool_schema.get('const')
                if (set(branch) != {'type', 'properties', 'required', 'additionalProperties'} or
                        branch.get('type') != 'object' or branch.get('additionalProperties') is not False or
                        props.get('tool') != {'const': tool} or
                        set(props) != {'tool', 'arguments'} or not isinstance(tool, str) or tool not in parameters or
                        props.get('arguments') != parameters[tool] or
                        set(branch.get('required', [])) != {'tool', 'arguments'}):
                    break
                names.append(tool)
            else:
                return {'type': 'object', 'properties': {
                    'tool': {'type': 'string', 'enum': names},
                    'arguments': {'type': 'object', 'description':
                        'Use the exact parameters schema of the tool named in source.tool; '
                        'all named tools are defined in this session. Server validates the full schema.'}},
                    'required': ['tool', 'arguments'], 'additionalProperties': False}
        return {k: project(v) for k, v in node.items()}

    return project(deepcopy(definitions))


def dashboard_context(snapshot):
    """Keep chart provenance/configuration, not full materialized row arrays."""
    state = deepcopy(snapshot or {})
    numbers = chart_display_numbers(state.get('views', []))
    for view in state.get('views', []):
        if view.get('id') in numbers:
            view['display_number'] = numbers[view['id']]
        if isinstance(view.get('data'), list):
            rows = view.pop('data')
            view['data_summary'] = {'returned_rows': len(rows), 'rows_included': False,
                                    'access': 'inspect_dashboard(view_id, include_data=true) for bounded data'}
    return state


def dataset_context(description):
    """Reference exact redundant list indexes, retaining all distinct semantics."""
    result = deepcopy(description)
    for key, index in description.items():
        if not key.endswith('_index') or not isinstance(index, dict) or not index:
            continue
        for collection_name, entries in description.items():
            if not isinstance(entries, list) or len(entries) != len(index):
                continue
            for field in ('id', 'name', 'field'):
                if all(isinstance(e, dict) and isinstance(e.get(field), str) for e in entries):
                    candidate = {e[field]: e for e in entries}
                    if candidate == index:
                        result[key] = {'entries_from': collection_name, 'key_field': field}
                        break
            if result[key] != index:
                break
    return result


def tool_output_event(call_id, output):
    """Explicit delivery failure, never silently cut rows or undo a valid commit."""
    event = {'type': 'conversation.item.create', 'item': {
        'type': 'function_call_output', 'call_id': call_id, 'output': compact_json(output)}}
    try:
        encode_provider_event(dict(event_id='0' * 32, **event))
    except ProviderMessageTooLarge:
        bounded = {key: output[key] for key in ('execution_status', 'commit_status',
                   'state_changed', 'committed', 'dashboard_revision') if key in output}
        bounded.update(success=False, payload=None, error={
            'code': 'provider_result_too_large',
            'message': 'Tool execution outcome is recorded above, but its full result exceeds '
                       'the provider message budget. No result rows were delivered. '
                       'Existing committed charts remain valid. Inspect one view with '
                       'include_data=false, or issue a narrower aggregate query; do not '
                       'repeat a successful mutation or claim unseen numerical results.'})
        event['item']['output'] = compact_json(bounded)
        encode_provider_event(dict(event_id='0' * 32, **event))
    return event
