"""Validated boundary for explicitly configured, trusted Python interfaces.

This is not a sandbox. Never accept an interface path from model arguments.
All calls (including close) serialize on the adapter's reentrant lock.
"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import importlib.util
import json
import math
from pathlib import Path
import sys
import threading
import uuid

from jsonschema import Draft202012Validator


def _json(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (float, Decimal)):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError('Non-finite numeric value')
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return {k: _json(v) for k, v in value.items()}
    raise ValueError('Value is not JSON-safe')


class DatasetAdapter:
    def __init__(self, interface, module_name=None):
        self._interface = interface
        self._module_name = module_name
        self._lock = threading.RLock()
        self._closed = False
        for name in ('describe', 'tool_definitions', 'execute', 'close'):
            if not callable(getattr(interface, name, None)):
                raise ValueError('Missing interface method: ' + name)
        self._description = _json(interface.describe())
        for key in ('dataset_id', 'version', 'description'):
            if not isinstance(self._description.get(key), str) or not self._description[key]:
                raise ValueError('Invalid descriptor ' + key)
        self._version = self._description['version']
        self._definitions = _json(interface.tool_definitions())
        if not isinstance(self._definitions, list):
            raise ValueError('Tool definitions must be a list')
        self._validators = {}
        for definition in self._definitions:
            name = definition.get('name')
            if not isinstance(name, str) or not name or name in self._validators:
                raise ValueError('Invalid or duplicate tool name')
            if not isinstance(definition.get('description'), str):
                raise ValueError('Tool description required')
            if definition.get('read_only') is not True:
                raise ValueError('Dataset tools must declare read_only: true')
            schema = definition.get('parameters')
            try:
                Draft202012Validator.check_schema(schema)
                if not isinstance(schema, dict) or schema.get('type') != 'object':
                    raise ValueError('Tool parameters must be object schema')
                self._validators[name] = Draft202012Validator(schema)
            except Exception as exc:
                raise ValueError('Invalid parameter schema') from exc

    @property
    def description(self):
        return deepcopy(self._description)

    @property
    def definitions(self):
        return deepcopy(self._definitions)

    def execute(self, name, arguments, scope=None):
        with self._lock:
            try:
                if self._closed:
                    raise ValueError('Dataset closed')
                if name not in self._validators:
                    raise ValueError('Unknown dataset tool')
                arguments = _json(arguments)
                self._validators[name].validate(arguments)
                result = _json(self._interface.execute(name, arguments, _json(scope)))
                if not isinstance(result, dict) or type(result.get('success')) is not bool:
                    raise ValueError('Result success must be boolean')
                if result.get('dataset_version') != self._version:
                    raise ValueError('Dataset version mismatch')
                if result['success']:
                    rows, columns = result.get('rows'), result.get('columns')
                    if not isinstance(rows, list) or not isinstance(columns, dict) or type(result.get('truncated')) is not bool:
                        raise ValueError('Invalid tabular result')
                    for metadata in columns.values():
                        if not isinstance(metadata, dict) or metadata.get('type') not in {'nominal', 'ordinal', 'quantitative', 'temporal'}:
                            raise ValueError('Invalid column metadata')
                    for row in rows:
                        if not isinstance(row, dict) or set(row) != set(columns):
                            raise ValueError('Row and column schema mismatch')
                        for field, value in row.items():
                            if isinstance(value, (dict, list)):
                                raise ValueError('Table cells must be scalar')
                            if columns[field]['type'] == 'quantitative' and value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                                raise ValueError('Non-numeric quantitative column')
                            if columns[field]['type'] == 'temporal' and value is not None:
                                if not isinstance(value, str):
                                    raise ValueError('Temporal cells require ISO date or datetime strings')
                                try:
                                    date.fromisoformat(value)
                                except ValueError:
                                    try:
                                        datetime.fromisoformat(value)
                                    except ValueError as exc:
                                        raise ValueError('Invalid ISO temporal cell') from exc
                elif not isinstance(result.get('error'), dict):
                    raise ValueError('Failure requires structured error')
                return result
            except Exception as exc:
                return {'success': False, 'dataset_version': self._version,
                        'error': {'code': 'dataset_error', 'message': str(exc)}}

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                try:
                    self._interface.close()
                finally:
                    if self._module_name is not None:
                        sys.modules.pop(self._module_name, None)


def load_dataset(interface_path: Path, config: dict) -> DatasetAdapter:
    path = Path(interface_path).resolve(strict=True)
    spec = importlib.util.spec_from_file_location('trusted_dataset_' + uuid.uuid4().hex, path)
    if spec is None or spec.loader is None:
        raise ValueError('Unable to load interface')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    interface = None
    try:
        spec.loader.exec_module(module)
        factory = getattr(module, 'open_dataset', None)
        if not callable(factory):
            raise ValueError('Interface requires open_dataset(config)')
        interface = factory(deepcopy(config))
        return DatasetAdapter(interface, module_name=spec.name)
    except BaseException:
        try:
            if callable(getattr(interface, 'close', None)):
                interface.close()
        finally:
            sys.modules.pop(spec.name, None)
        raise
