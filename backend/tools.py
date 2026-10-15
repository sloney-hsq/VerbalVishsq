"""Dataset-neutral model tools. Every mutating call is atomic within its draft."""
from copy import deepcopy
from datetime import datetime
from math import isfinite
import uuid

from jsonschema import Draft202012Validator


def _object(properties=None, required=()):
    return {'type': 'object', 'properties': properties or {},
            'required': list(required), 'additionalProperties': False}


_STRING = {'type': 'string', 'minLength': 1}
_SOURCE = _object({'tool': _STRING, 'arguments': {'type': 'object'}}, ('tool', 'arguments'))
_CHART = {'source': _SOURCE, 'chart_type': {'enum': ['bar', 'line', 'scatter']},
          'x': _STRING, 'y': _STRING, 'series': {'type': ['string', 'null'], 'minLength': 1},
          'title': {'type': 'string'}}
_FILTER = _object({'field': _STRING, 'op': _STRING,
                   'value': {'type': ['string', 'number', 'boolean', 'null']}}, ('field', 'op'))
_PUBLIC = [
    ('describe_dataset', 'Describe the active dataset, metrics, fields and shared filters.', _object()),
    ('create_chart', 'Create a chart from a registered read-only dataset tool.', _object(_CHART, ('source', 'chart_type', 'x', 'y'))),
    ('update_chart', 'Update a chart; omitted properties are preserved.', _object({'view_id': _STRING, **_CHART}, ('view_id',))),
    ('delete_chart', 'Delete a chart by its view ID.', _object({'view_id': _STRING}, ('view_id',))),
    ('set_analysis_filters', 'Replace shared filters and recompute every chart atomically.', _object({'filters': {'type': 'array', 'items': _FILTER}}, ('filters',))),
    ('highlight_chart', 'Highlight one chart or clear highlighting with a null view_id.', _object({'view_id': {'type': ['string', 'null']}, 'element': {'type': ['object', 'null']}, 'dim_others': {'type': 'boolean'}}, ('view_id',))),
    ('inspect_dashboard', 'Inspect the current draft dashboard without changing it.', _object()),
    ('undo_dashboard', 'Undo the last committed change. Must be the only mutation in the batch.', _object()),
]
_MUTATING = {name for name, _, _ in _PUBLIC} - {'describe_dataset', 'inspect_dashboard'}


class Toolbox:
    def __init__(self, dataset, dashboard):
        self.dataset = dataset
        self.dashboard = dashboard
        self._description = deepcopy(dataset.description)
        snapshot = dashboard.snapshot()
        if (snapshot['dataset_id'], snapshot['dataset_version']) != (self._description['dataset_id'], self._description['version']):
            raise ValueError('Dashboard and dataset identity/version mismatch')
        self._definitions = {name: {'name': name, 'description': description, 'parameters': deepcopy(schema)}
                             for name, description, schema in _PUBLIC}
        self._domain_names = set()
        for definition in dataset.definitions:
            name = definition['name']
            if name in self._definitions:
                raise ValueError('Dataset tool name collides with a public tool: ' + name)
            if definition.get('read_only') is not True:
                raise ValueError('Chart sources must be read-only dataset tools')
            self._definitions[name] = {key: deepcopy(definition[key]) for key in ('name', 'description', 'parameters')}
            self._domain_names.add(name)
        self._validators = {name: Draft202012Validator(definition['parameters']) for name, definition in self._definitions.items()}

    def schemas(self):
        return deepcopy(list(self._definitions.values()))

    def effect_category(self, name):
        """Classify registered effects without exposing dataset-specific tool names."""
        if name not in self._definitions:
            raise ValueError('Unknown tool: ' + str(name))
        return 'read_only' if name in self._domain_names or name not in _MUTATING else 'mutating'

    def execute(self, name, args, draft):
        before = None
        try:
            self.dashboard.validate_draft(draft, mutation=name in _MUTATING)
            before, dirty = deepcopy(draft.document), draft.dirty
            if name not in self._validators:
                raise ValueError('Unknown tool: ' + str(name))
            arguments = deepcopy(args)
            self._validators[name].validate(arguments)
            if name in self._domain_names:
                payload = self.dataset.execute(name, arguments, deepcopy(draft.document['filters']))
                if payload.get('dataset_version') != self._description['version']:
                    raise ValueError('Dataset result version mismatch')
                if not payload['success']:
                    return {'success': False, 'payload': deepcopy(payload), 'error': deepcopy(payload['error'])}
            else:
                payload = getattr(self, '_' + name)(arguments, draft)
            if name in _MUTATING and draft.document != before:
                draft.dirty = True
            return {'success': True, 'payload': deepcopy(payload)}
        except Exception as exc:
            if before is not None:
                draft.document = before
                draft.dirty = dirty
            return {'success': False, 'payload': None,
                    'error': {'code': 'tool_error', 'message': str(exc)}}

    def _query(self, name, arguments, filters):
        if name not in self._domain_names:
            raise ValueError('Chart source must name a registered dataset tool')
        self._validators[name].validate(arguments)
        result = self.dataset.execute(name, deepcopy(arguments), deepcopy(filters))
        if not result.get('success'):
            raise ValueError(result.get('error', {}).get('message', 'Dataset query failed'))
        if result.get('dataset_version') != self._description['version']:
            raise ValueError('Dataset result version mismatch')
        return result

    def _view(self, document, view_id):
        for view in document['views']:
            if view['id'] == view_id:
                return view
        raise ValueError('Unknown view_id: ' + view_id)

    def _render(self, config, filters):
        result = self._query(config['source']['tool'], config['source']['arguments'], filters)
        columns = result['columns']
        requested = [config['x'], config['y']]
        if config.get('series') is not None:
            requested.append(config['series'])
        if any(field not in columns for field in requested):
            raise ValueError('Chart encoding references a missing result column')
        x_type, y_type = columns[config['x']]['type'], columns[config['y']]['type']
        allowed_x = {'bar': {'nominal', 'ordinal', 'temporal'},
                     'line': {'temporal', 'ordinal', 'quantitative'},
                     'scatter': {'quantitative'}}
        if y_type != 'quantitative' or x_type not in allowed_x[config['chart_type']]:
            raise ValueError('Chart encoding types do not match chart semantics')
        if config.get('series') is not None and columns[config['series']]['type'] not in {'nominal', 'ordinal'}:
            raise ValueError('Series must use a nominal or ordinal column')
        return {'chart_type': config['chart_type'], 'x_field': config['x'], 'y_field': config['y'],
                'color': config.get('series'), 'title': config.get('title', ''),
                'source': deepcopy(config['source']), 'data': deepcopy(result['rows']),
                'columns': deepcopy(columns), 'truncated': result['truncated']}

    def _describe_dataset(self, args, draft):
        return self._description

    def _inspect_dashboard(self, args, draft):
        return draft.document

    def _create_chart(self, args, draft):
        view = {'id': uuid.uuid4().hex, 'highlighted': False,
                **self._render(args, draft.document['filters'])}
        draft.document['views'].append(view)
        return view

    def _update_chart(self, args, draft):
        view = self._view(draft.document, args['view_id'])
        config = {'source': view['source'], 'chart_type': view['chart_type'],
                  'x': view['x_field'], 'y': view['y_field'], 'series': view['color'], 'title': view['title']}
        config.update({key: value for key, value in args.items() if key != 'view_id'})
        view.update(self._render(config, draft.document['filters']))
        return view

    def _delete_chart(self, args, draft):
        view = self._view(draft.document, args['view_id'])
        draft.document['views'].remove(view)
        if view['id'] in draft.document['highlighted']:
            draft.document['highlighted'].remove(view['id'])
        if not draft.document['highlighted']:
            draft.document['highlight_element'] = None
            draft.document['dim_others'] = False
        return {'deleted': view['id']}

    def _validate_filters(self, filters):
        descriptor = self._description.get('filters', {})
        fields, operators = descriptor.get('fields', []), descriptor.get('operators', [])
        metadata = {}
        for resource in self._description.get('resources', []):
            for field, definition in resource.get('fields', {}).items():
                if field in metadata and metadata[field].get('type') != definition.get('type'):
                    raise ValueError('Ambiguous shared filter field metadata: ' + field)
                metadata[field] = definition
        for item in filters:
            if item['field'] not in fields or item['op'] not in operators:
                raise ValueError('Unsupported shared filter field or operator')
            if item['op'] != 'is_null' and 'value' not in item:
                raise ValueError('Filter requires a scalar value')
            if item['op'] == 'is_null':
                continue
            value = item['value']
            field_type = metadata.get(item['field'], {}).get('type')
            if value is None:
                if item['op'] not in {'eq', 'neq'}:
                    raise ValueError('Null is valid only for equality or null filters')
            elif field_type == 'temporal':
                if not isinstance(value, str):
                    raise ValueError('Temporal filters require an ISO date or datetime string')
                try:
                    datetime.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError('Temporal filters require a valid ISO date or datetime') from exc
            elif field_type == 'quantitative':
                if type(value) not in {int, float} or not isfinite(value):
                    raise ValueError('Quantitative filters require a finite number')
            elif type(value) is float and not isfinite(value):
                raise ValueError('Filter values must be finite')

    def _set_analysis_filters(self, args, draft):
        filters = args['filters']
        self._validate_filters(filters)
        # Render into private candidates first; no partial updates if any source fails.
        views = []
        for view in draft.document['views']:
            config = {'source': view['source'], 'chart_type': view['chart_type'], 'x': view['x_field'],
                      'y': view['y_field'], 'series': view['color'], 'title': view['title']}
            views.append({**view, **self._render(config, filters)})
        draft.document['views'] = views
        draft.document['filters'] = deepcopy(filters)
        return draft.document

    def _highlight_chart(self, args, draft):
        view_id = args['view_id']
        if view_id is not None:
            self._view(draft.document, view_id)
        for view in draft.document['views']:
            view['highlighted'] = view['id'] == view_id
        draft.document['highlighted'] = [view_id] if view_id is not None else []
        draft.document['highlight_element'] = deepcopy(args.get('element')) if view_id is not None else None
        draft.document['dim_others'] = args.get('dim_others', False) if view_id is not None else False
        return draft.document

    def _undo_dashboard(self, args, draft):
        self.dashboard.stage_undo(draft)
        return draft.document
