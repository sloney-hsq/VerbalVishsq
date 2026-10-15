"""Synthetic education assessments. Not an empirical study or student records."""
import hashlib
from pathlib import Path

import duckdb

GROUPS = {'cohort': 'nominal', 'subject': 'nominal', 'assessment_date': 'temporal'}
MEASURES = {'mean_score': ('AVG(score)', 'points'),
            'assessment_count': ('COUNT(*)', 'assessments'),
            'mean_attendance': ('AVG(attendance_pct)', '%'),
            'student_count': ('COUNT(DISTINCT student_id)', 'students')}


class Education:
    def __init__(self, config):
        path = Path(config.get('data_path', Path(__file__).with_name('data.csv'))).resolve(strict=True)
        self.version = 'education-1-' + hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        self.con = duckdb.connect(':memory:')
        try:
            self.con.execute('CREATE TABLE assessments AS SELECT * FROM read_csv_auto(?, header=true)', [str(path)])
            self.count = self.con.execute('SELECT COUNT(*) FROM assessments').fetchone()[0]
        except Exception:
            self.con.close()
            raise

    def describe(self):
        return {'dataset_id': 'education', 'version': self.version, 'synthetic': True,
                'description': 'Synthetic demonstration assessments, not real student or study data. NULL scores excluded from means.',
                'resources': [{'name': 'assessments', 'grain': 'student-subject assessment', 'row_count': self.count, 'row_label': 'assessments',
                               'fields': {**{k: {'type': v} for k, v in GROUPS.items()}, 'score': {'type': 'quantitative', 'unit': 'points'}, 'attendance_pct': {'type': 'quantitative', 'unit': '%'}}}],
                'metrics': {k: {'definition': v[0], 'unit': v[1]} for k, v in MEASURES.items()},
                'filters': {'fields': list(GROUPS), 'operators': ['eq', 'neq', 'gte', 'lte', 'is_null'], 'combination': 'AND; shared scope plus tool filters'}}

    def tool_definitions(self):
        return [{'name': 'summarize_learning', 'description': 'Compare synthetic assessment outcomes by cohort, subject or date.', 'read_only': True,
                 'parameters': {'type': 'object', 'properties': {
                     'group_by': {'type': 'string', 'enum': list(GROUPS)},
                     'measure': {'type': 'string', 'enum': list(MEASURES)},
                     'filters': {'type': 'array', 'items': {'type': 'object'}},
                     'limit': {'type': 'integer', 'minimum': 1, 'maximum': 500}},
                     'required': ['group_by', 'measure'], 'additionalProperties': False}}]

    def execute(self, name, arguments, scope=None):
        if name != 'summarize_learning':
            raise ValueError('Unknown education tool')
        group, measure = arguments['group_by'], arguments['measure']
        if group not in GROUPS or measure not in MEASURES:
            raise ValueError('Unsupported education field or measure')
        if scope is not None and not isinstance(scope, list):
            raise ValueError('Scope must be a list of filters')
        clauses, params = [], []
        for f in [*(scope or []), *arguments.get('filters', [])]:
            if not isinstance(f, dict) or set(f) - {'field', 'op', 'value'} or f.get('field') not in GROUPS:
                raise ValueError('Unsupported education filter')
            col, op = f['field'], f.get('op')
            if op == 'is_null':
                clauses.append(f'"{col}" IS NULL')
            elif op in {'eq', 'neq', 'gte', 'lte'}:
                if 'value' not in f or isinstance(f['value'], (list, dict)):
                    raise ValueError('Filter requires scalar value')
                if f['value'] is None and op in {'eq', 'neq'}:
                    clauses.append(f'"{col}" IS ' + ('NOT NULL' if op == 'neq' else 'NULL'))
                else:
                    clauses.append(f'"{col}" ' + {'eq':'=', 'neq':'<>', 'gte':'>=', 'lte':'<='}[op] + ' ?')
                    params.append(f['value'])
            else:
                raise ValueError('Unsupported filter operator')
        limit = arguments.get('limit', 100)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError('Invalid limit')
        where = ' AND '.join(clauses) or 'TRUE'
        rows = self.con.execute(f'SELECT "{group}", {MEASURES[measure][0]} FROM assessments WHERE {where} GROUP BY "{group}" ORDER BY "{group}" NULLS LAST LIMIT ?', [*params, limit+1]).fetchall()
        return {'success': True, 'dataset_version': self.version,
                'rows': [{group: r[0], measure: r[1]} for r in rows[:limit]],
                'columns': {group: {'type': GROUPS[group], 'label': group}, measure: {'type': 'quantitative', 'unit': MEASURES[measure][1]}},
                'truncated': len(rows) > limit}

    def close(self):
        self.con.close()


def open_dataset(config):
    return Education(config)
