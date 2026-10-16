"""Dataset-neutral model tools. Every mutating call is atomic within its draft."""
from copy import deepcopy
from datetime import datetime
from math import isfinite
import uuid

from jsonschema import Draft202012Validator
from jsonschema import ValidationError

from .chart_contract import normalize_visual, validate_visual
from .chart_patch import normalize_source_filters, execution_source, apply_analysis_patch, apply_visual_patch
from .filter_contract import normalize_filters, validate_filter_conflicts
from .selection import selection_filters, match_predicate


def _object(properties=None, required=()):
    return {'type': 'object', 'properties': properties or {},
            'required': list(required), 'additionalProperties': False}


_STRING = {'type': 'string', 'minLength': 1}
_SOURCE = _object({'tool': _STRING, 'arguments': {'type': 'object'}}, ('tool', 'arguments'))
_CHART = {'source': _SOURCE, 'chart_type': {'enum': ['bar', 'line', 'scatter']},
          'x': _STRING, 'y': _STRING, 'series': {'type': ['string', 'null'], 'minLength': 1},
          'title': {'type': 'string'}}
_FILTER = _object({'field': _STRING, 'op': _STRING,
                   'value': {}}, ('field', 'op'))
_FILTER_EDIT = {'type': 'object'}
_ENCODING = _object({key: (_STRING if key != 'tooltip' else {'type': 'array', 'items': _STRING})
                     for key in ('x', 'y', 'color', 'size', 'facet', 'tooltip')})
_VISUAL = _object({'type': {'enum': ['bar', 'line', 'scatter', 'heatmap', 'histogram', 'boxplot']},
                   'encoding': _ENCODING, 'stack': {'enum': ['none', 'zero', 'normalize']},
                   'sort': _object({'field': _STRING, 'direction': {'enum': ['asc', 'desc']}}, ('field', 'direction')),
                   'scales': _object({'x': {'enum': ['linear', 'log']}, 'y': {'enum': ['linear', 'log']},
                                      'resolve': {'enum': ['shared', 'independent']}})}, ('type', 'encoding'))
_VISUAL_PATHS = ['type', 'encoding.x', 'encoding.y', 'encoding.color', 'encoding.size',
                 'encoding.facet', 'encoding.tooltip', 'sort', 'stack', 'scales.x', 'scales.y', 'scales.resolve']
_VISUAL_SET = {**{f'encoding.{key}': value for key, value in _ENCODING['properties'].items()},
               'type': _VISUAL['properties']['type'], 'sort': _VISUAL['properties']['sort'],
               'stack': _VISUAL['properties']['stack'],
               'scales.x': {'enum': ['linear', 'log']}, 'scales.y': {'enum': ['linear', 'log']},
               'scales.resolve': {'enum': ['shared', 'independent']}}
_VISUAL_PATCH = _object({'set': _object(_VISUAL_SET),
                         'unset': {'type': 'array', 'items': {'enum': _VISUAL_PATHS}, 'uniqueItems': True}})
_FILTER_CHANGES = _object({'upsert': {'type': 'array', 'items': _FILTER_EDIT},
                           'remove': {'type': 'array', 'items': _STRING, 'uniqueItems': True}})
_MEASURE_CHANGES = _object({'upsert': {'type': 'array', 'items': {'type': 'object'}},
                            'remove': {'type': 'array', 'items': _STRING, 'uniqueItems': True}})
_ANALYSIS_PATCH = {'oneOf': [
    _object({'set': {'type': 'object'}, 'unset': {'type': 'array', 'items': _STRING, 'uniqueItems': True},
             'filter_changes': _FILTER_CHANGES, 'measure_changes': _MEASURE_CHANGES}),
    _object({'replace_source': _SOURCE, 'inherit_scope': {'const': True}}, ('replace_source', 'inherit_scope'))]}
_CREATE = _object({**_CHART, 'visual': _VISUAL, 'activate': {'type': 'boolean'}}, ('source',))
_CREATE['anyOf'] = [{'required': ['visual']}, {'required': ['chart_type', 'x', 'y']}]
_UPDATE = _object({'view_id': _STRING, **_CHART, 'analysis_patch': _ANALYSIS_PATCH,
                   'visual_patch': _VISUAL_PATCH}, ('view_id',))
_FORK = _object({'view_id': _STRING, 'analysis_patch': _ANALYSIS_PATCH,
                 'visual_patch': _VISUAL_PATCH, 'title': {'type': 'string'},
                 'scope_mode': {'enum': ['snapshot', 'linked']}}, ('view_id',))
_SELECTION = _object({'source_view_id': _STRING, 'source_revision': {'type': 'integer', 'minimum': 1},
                      'predicate': {'type': 'array', 'minItems': 1, 'items': _FILTER},
                      'target_view_ids': {'type': 'array', 'minItems': 1, 'uniqueItems': True, 'items': _STRING},
                      'effect': {'enum': ['highlight', 'filter', 'clear']}},
                     ('source_view_id', 'source_revision', 'target_view_ids', 'effect'))
_PUBLIC = [
    ('describe_dataset', 'Describe the active dataset, metrics, fields and shared filters.', _object()),
    ('create_chart', 'Create a typed chart from a registered read-only dataset tool.', _CREATE),
    ('update_chart', 'Patch an existing chart; omitted properties are preserved.', _UPDATE),
    ('fork_chart', 'Copy a chart with snapshot or linked scope.', _FORK),
    ('set_selection', 'Apply or clear a marked source selection on explicit target views.', _SELECTION),
    ('delete_chart', 'Delete a chart by its view ID.', _object({'view_id': _STRING}, ('view_id',))),
    ('set_analysis_filters', 'Replace shared filters and recompute every chart atomically.', _object({'filters': {'type': 'array', 'items': {'type': 'object'}}}, ('filters',))),
    ('highlight_chart', 'Highlight one chart or clear highlighting with a null view_id.', _object({'view_id': {'type': ['string', 'null']}, 'element': {'type': ['object', 'null']}, 'dim_others': {'type': 'boolean'}}, ('view_id',))),
    ('inspect_dashboard', 'Inspect dashboard summary or bounded view data.', _object({'view_id': _STRING, 'include_data': {'type': 'boolean'}})),
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
        source_branches = [_object({'tool': {'const': definition['name']},
                                    'arguments': deepcopy(definition['parameters'])}, ('tool', 'arguments'))
                           for definition in dataset.definitions]
        self._definitions['create_chart']['parameters']['properties']['source'] = {'oneOf': source_branches}
        self._definitions['update_chart']['parameters']['properties']['source'] = {'oneOf': source_branches}
        for name in ('update_chart', 'fork_chart'):
            patch = self._definitions[name]['parameters']['properties']['analysis_patch']
            patch['oneOf'][1]['properties']['replace_source'] = {'oneOf': source_branches}
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
            message = str(exc)
            code = message.split(':', 1)[0]
            if code not in {'INVALID_FILTER_VALUE', 'INVALID_MEASURE', 'INVALID_COMPARISON', 'INCOMPATIBLE_PERIODS', 'EMPTY_REFERENCE_POPULATION', 'FILTER_CONFLICT', 'INCOMPATIBLE_GRAIN',
                            'INCOMPATIBLE_ENCODING', 'RESULT_TOO_LARGE', 'INVALID_SELECTION', 'STALE_SOURCE_VIEW'}:
                code = 'tool_error'
            error = {'code': code, 'message': message}
            if isinstance(exc, ValidationError):
                error['path'] = list(exc.absolute_path)
            return {'success': False, 'payload': None, 'error': error}

    def _query(self, name, arguments, filters):
        if name not in self._domain_names:
            raise ValueError('Chart source must name a registered dataset tool')
        clean = execution_source({'tool': name, 'arguments': arguments})['arguments']
        self._validators[name].validate(clean)
        result = self.dataset.execute(name, deepcopy(clean), deepcopy(filters))
        if not result.get('success'):
            error = result.get('error', {})
            code = error.get('code', 'dataset_error')
            message = error.get('message', 'Dataset query failed')
            if code in {'INVALID_FILTER_VALUE', 'FILTER_CONFLICT', 'INCOMPATIBLE_GRAIN',
                        'INCOMPATIBLE_ENCODING', 'RESULT_TOO_LARGE'}:
                raise ValueError(f'{code}: {message}')
            raise ValueError(message)
        if result.get('dataset_version') != self._description['version']:
            raise ValueError('Dataset result version mismatch')
        return result

    def _view(self, document, view_id):
        for view in document['views']:
            if view['id'] == view_id:
                return view
        raise ValueError('Unknown view_id: ' + view_id)

    def _render(self, config, filters, *, stored_result=None):
        source = normalize_source_filters(config['source'])
        if source['tool'] not in self._domain_names:
            raise ValueError('Chart source must name a registered dataset tool')
        result = stored_result or self._query(source['tool'], source['arguments'], filters)
        visual = validate_visual(normalize_visual(config), result)
        if result.get('truncated') and visual['type'] in {'line', 'heatmap', 'histogram', 'boxplot'}:
            raise ValueError('RESULT_TOO_LARGE: chart source is truncated; narrow range or use top_k')
        encoding = visual['encoding']
        return {'chart_type': visual['type'], 'x_field': encoding.get('x'), 'y_field': encoding.get('y'),
                'color': encoding.get('color'), 'title': config.get('title', ''),
                'source': source, 'visual': visual, 'data': deepcopy(result['rows']),
                'columns': deepcopy(result['columns']), 'truncated': result['truncated'],
                'result_kind': result.get('result_kind', 'table'), 'metadata': deepcopy(result.get('metadata', {}))}

    def _stored_result(self, view):
        return {'rows': deepcopy(view['data']), 'columns': deepcopy(view['columns']),
                'truncated': view['truncated'], 'result_kind': view.get('result_kind', 'table'),
                'metadata': deepcopy(view.get('metadata', {}))}

    def _scope_for(self, view, shared_filters):
        base = view.get('scope_filters', []) if view.get('scope_mode') == 'snapshot' else shared_filters
        return [*deepcopy(base), *(deepcopy(item) for filters in view.get('selection_filters', {}).values() for item in filters)]

    def _describe_dataset(self, args, draft):
        return self._description

    def _inspect_dashboard(self, args, draft):
        document = deepcopy(draft.document)
        if args.get('view_id'):
            selected = self._view(document, args['view_id'])
            document['views'] = [selected]
        if not args.get('include_data'):
            for view in document['views']:
                view.pop('data', None)
        else:
            for view in document['views']:
                if len(view.get('data', [])) > 200:
                    view['data'] = view['data'][:200]
                    view['data_truncated_for_inspection'] = True
        return document

    def _create_chart(self, args, draft):
        view = {'id': uuid.uuid4().hex, 'highlighted': False,
                'view_revision': 1, 'scope_mode': 'linked', 'selection_filters': {},
                'selection_highlights': {}, **self._render(args, draft.document['filters'])}
        draft.document['views'].append(view)
        if args.get('activate', True):
            draft.document['active_view_id'] = view['id']
        return view

    def _update_chart(self, args, draft):
        view = self._view(draft.document, args['view_id'])
        if 'analysis_patch' in args and 'source' in args or 'visual_patch' in args and any(key in args for key in ('chart_type', 'x', 'y', 'series')):
            raise ValueError('INCOMPATIBLE_ENCODING: mixed legacy and patch update')
        source = apply_analysis_patch(view['source'], args['analysis_patch']) if 'analysis_patch' in args else deepcopy(args.get('source', view['source']))
        visual = apply_visual_patch(view['visual'], args['visual_patch']) if 'visual_patch' in args else deepcopy(view['visual'])
        if any(key in args for key in ('chart_type', 'x', 'y', 'series')):
            visual = normalize_visual({'chart_type': args.get('chart_type', view['chart_type']),
                'x': args.get('x', view['x_field']), 'y': args.get('y', view['y_field']),
                'series': args.get('series', view['color'])})
        config = {'source': source, 'visual': visual, 'title': args.get('title', view['title'])}
        source_changed = execution_source(source) != execution_source(view['source'])
        rendered = self._render(config, self._scope_for(view, draft.document['filters']),
                                stored_result=None if source_changed else self._stored_result(view))
        changed = [key for key in ('source', 'visual', 'title') if rendered[key] != view[key]]
        if changed:
            view.update(rendered)
            view['view_revision'] = view.get('view_revision', 1) + 1
        return {**view, 'changed_fields': changed, 'effective_source': deepcopy(view['source'])}

    def _fork_chart(self, args, draft):
        original = self._view(draft.document, args['view_id'])
        mode = args.get('scope_mode', 'snapshot')
        if mode == 'snapshot' and original.get('scope_mode') != 'snapshot':
            effective_scope = self._scope_for(original, draft.document['filters'])
            original['scope_mode'] = 'snapshot'
            original['scope_filters'] = effective_scope
            original['selection_filters'] = {}
            original['view_revision'] += 1
        clone = deepcopy(original)
        clone['id'] = uuid.uuid4().hex
        clone['highlighted'] = False
        if mode == 'snapshot':
            clone['selection_filters'] = {}
            rules = clone.get('metadata', {}).get('quantile_rules', [])
            if rules:
                filters = clone['source']['arguments'].get('filters', [])
                remaining, materialized = list(rules), []
                kept = []
                for item in filters:
                    if item.get('op') != 'quantile_between':
                        kept.append(item); continue
                    match = next((rule for rule in remaining if rule.get('field') == item.get('field')
                                  and rule.get('probabilities') == item.get('value')), None)
                    if match is None:
                        raise ValueError('INVALID_FILTER_VALUE: quantile provenance does not match source rule')
                    remaining.remove(match)
                    materialized.append((item, match))
                if remaining:
                    raise ValueError('INVALID_FILTER_VALUE: unresolved quantile metadata during snapshot')
                filters = kept
                for source_rule, rule in materialized:
                    rule = {**rule, 'id': source_rule.get('id')}
                    for side, op in (('lower', 'gte'), ('upper', 'lte')):
                        if side in rule.get('bounds', {}):
                            filters.append({'id': uuid.uuid4().hex, 'field': rule['field'], 'op': op,
                                'value': rule['bounds'][side]})
                # provenance is stored outside executable filter shapes
                clone['source']['arguments']['filters'] = filters
                clone.setdefault('metadata', {})['materialized_quantile_rules'] = [
                    {**rule, 'id': source_rule.get('id')} for source_rule, rule in materialized]
        clone['selection_highlights'] = {}
        clone['view_revision'] = 1
        clone['scope_mode'] = mode
        if mode == 'linked':
            clone.pop('scope_filters', None)
            if original.get('scope_mode') == 'snapshot':
                clone.update(self._render({'source': clone['source'], 'visual': clone['visual'], 'title': clone['title']},
                                          self._scope_for(clone, draft.document['filters'])))
        draft.document['views'].append(clone)
        if any(key in args for key in ('analysis_patch', 'visual_patch', 'title')):
            update = {'view_id': clone['id']}
            update.update({key: args[key] for key in ('analysis_patch', 'visual_patch', 'title') if key in args})
            self._update_chart(update, draft)
        return clone

    def _delete_chart(self, args, draft):
        view = self._view(draft.document, args['view_id'])
        draft.document['views'].remove(view)
        for target in draft.document['views']:
            if view['id'] in target.get('selection_filters', {}):
                target.setdefault('selection_source_status', {})[view['id']] = 'source_removed'
        if draft.document.get('active_view_id') == view['id']:
            draft.document['active_view_id'] = draft.document['views'][-1]['id'] if draft.document['views'] else None
        if view['id'] in draft.document['highlighted']:
            draft.document['highlighted'].remove(view['id'])
        if not draft.document['highlighted']:
            draft.document['highlight_element'] = None
            draft.document['dim_others'] = False
        return {'deleted': view['id']}

    def _validate_filters(self, filters):
        field_index = self._description.get('field_index')
        if isinstance(field_index, dict):
            normalized = normalize_filters(filters, field_index)
            validate_filter_conflicts(normalized)
            return
        descriptor = self._description.get('filters', {})
        fields, operators = descriptor.get('fields', []), descriptor.get('operators', [])
        metadata = {}
        for resource in self._description.get('resources', []):
            for field, definition in resource.get('fields', {}).items():
                if field in metadata and metadata[field].get('type') != definition.get('type'):
                    raise ValueError('Ambiguous shared filter field metadata: ' + field)
                metadata[field] = definition
        for item in filters:
            if item.get('op') == 'or':
                raise ValueError('INVALID_FILTER_VALUE: bounded OR is not declared by this dataset')
            if item['field'] not in fields or item['op'] not in operators:
                raise ValueError('Unsupported shared filter field or operator')
            if item['op'] != 'is_null' and 'value' not in item:
                raise ValueError('Filter requires a scalar value')
            if item['op'] == 'is_null':
                continue
            value = item['value']
            if isinstance(value, (dict, list)):
                raise ValueError('Filter requires a scalar value')
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
        if filters == draft.document['filters']:
            return draft.document
        # Render into private candidates first; no partial updates if any source fails.
        views = []
        for view in draft.document['views']:
            if view.get('scope_mode') == 'snapshot':
                views.append(view)
                continue
            config = {'source': view['source'], 'visual': view['visual'], 'title': view['title']}
            views.append({**view, **self._render(config, self._scope_for(view, filters)), 'view_revision': view.get('view_revision', 1) + 1})
        draft.document['views'] = views
        draft.document['filters'] = deepcopy(filters)
        return draft.document

    def _set_selection(self, args, draft):
        source = next((view for view in draft.document['views'] if view['id'] == args['source_view_id']), None)
        if source is None and args['effect'] != 'clear':
            raise ValueError('INVALID_SELECTION: source view was removed')
        if source is not None and source.get('view_revision') != args['source_revision']:
            raise ValueError('STALE_SOURCE_VIEW: source view revision changed')
        target_ids = args['target_view_ids']
        if args['source_view_id'] in target_ids or len(set(target_ids)) != len(target_ids):
            raise ValueError('INVALID_SELECTION: targets must be distinct from source')
        targets = [self._view(draft.document, view_id) for view_id in target_ids]
        effect = args['effect']
        raw_filters = selection_filters(source, args.get('predicate')) if effect == 'filter' else []
        if effect == 'highlight':
            match_predicate(source, args.get('predicate'))
        if effect == 'filter':
            self._validate_filters(raw_filters)
        replacements = {}
        for target in targets:
            candidate = deepcopy(target)
            if effect == 'highlight':
                match_predicate(candidate, args['predicate'])
                candidate.setdefault('selection_highlights', {})[args['source_view_id']] = deepcopy(args['predicate'])
            else:
                had_selection = args['source_view_id'] in candidate.get('selection_filters', {}) or args['source_view_id'] in candidate.get('selection_highlights', {})
                if effect == 'clear' and not had_selection:
                    replacements[target['id']] = candidate
                    continue
                candidate.setdefault('selection_filters', {}).pop(args['source_view_id'], None)
                candidate.setdefault('selection_highlights', {}).pop(args['source_view_id'], None)
                candidate.setdefault('selection_source_status', {}).pop(args['source_view_id'], None)
                if effect == 'filter':
                    candidate['selection_filters'][args['source_view_id']] = deepcopy(raw_filters)
                config = {'source': candidate['source'], 'visual': candidate['visual'], 'title': candidate['title']}
                candidate.update(self._render(config, self._scope_for(candidate, draft.document['filters'])))
                candidate['view_revision'] += 1
            replacements[target['id']] = candidate
        draft.document['views'] = [replacements.get(view['id'], view) for view in draft.document['views']]
        return {'source_view_id': args['source_view_id'], 'target_view_ids': target_ids, 'effect': effect,
                'effective_filters': raw_filters}

    def _highlight_chart(self, args, draft):
        view_id = args['view_id']
        if view_id is not None:
            view = self._view(draft.document, view_id)
            if args.get('element') is not None:
                from .selection import legacy_highlight_matches
                legacy_highlight_matches(view, args['element'])
        for view in draft.document['views']:
            view['highlighted'] = view['id'] == view_id
        draft.document['highlighted'] = [view_id] if view_id is not None else []
        draft.document['highlight_element'] = deepcopy(args.get('element')) if view_id is not None else None
        draft.document['dim_others'] = args.get('dim_others', False) if view_id is not None else False
        return draft.document

    def _undo_dashboard(self, args, draft):
        self.dashboard.stage_undo(draft)
        return draft.document
