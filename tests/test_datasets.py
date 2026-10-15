"""Boundary and hand-calculated domain regression tests."""
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def loader():
    assert (ROOT / 'backend/analytics.py').exists(), 'dataset boundary not implemented'
    return importlib.import_module('refactor_next.backend.analytics').load_dataset


def test_education_real_csv_limits_filters_and_metadata():
    ds = loader()(ROOT / 'datasets/education/interface.py', {})
    try:
        result = ds.execute('summarize_learning', {'group_by': 'subject', 'measure': 'mean_score'})
        assert result['success']
        assert result['rows'] == [{'subject': 'Math', 'mean_score': 75.0}, {'subject': 'Science', 'mean_score': 85.0}]
        assert result['columns']['mean_score']['unit'] == 'points'
        assert ds.description['synthetic'] is True
        assert ds.execute('summarize_learning', {'group_by': 'subject', 'measure': 'mean_score', 'limit': 1})['truncated']
        empty = ds.execute('summarize_learning', {'group_by': 'subject', 'measure': 'mean_score'}, [{'field': 'cohort', 'op': 'eq', 'value': "x' OR 1=1 --"}])
        assert empty['rows'] == []
        assert not ds.execute('summarize_learning', {'group_by': 'not_a_field', 'measure': 'mean_score'})['success']
        assert not ds.execute('summarize_learning', {'group_by': 'subject', 'measure': 'mean_score'}, [{'field': 'invalid', 'op': 'eq', 'value': 1}])['success']
    finally:
        ds.close()
    assert not ds.execute('summarize_learning', {})['success']


def custom(tmp_path, *, schema=None, result=None, duplicate=False):
    schema = schema or {'type': 'object', 'properties': {}, 'additionalProperties': False}
    result = result or {'success': True, 'dataset_version': 'v1', 'rows': [{'数 值': 2}], 'columns': {'数 值': {'type': 'quantitative'}}, 'truncated': False}
    definition = {'name': 'custom', 'description': 'custom', 'parameters': schema, 'read_only': True}
    path = tmp_path / 'interface.py'
    path.write_text('class Dataset:\n    def describe(self): return '+repr({'dataset_id':'custom','version':'v1','description':'test'})+'\n    def tool_definitions(self): return '+repr([definition] * (2 if duplicate else 1))+'\n    def execute(self, name, arguments, scope): return '+repr(result)+'\n    def close(self): pass\ndef open_dataset(config): return Dataset()\n', encoding='utf-8')
    return path


def test_custom_interface_and_detached_boundary(tmp_path):
    ds = loader()(custom(tmp_path), {})
    assert ds.execute('custom', {})['rows'] == [{'数 值': 2}]
    ds.description['version'] = 'changed'
    ds.definitions.clear()
    assert ds.execute('custom', {})['dataset_version'] == 'v1'
    assert not ds.execute('custom', {'unexpected': True})['success']
    ds.close()


@pytest.mark.parametrize('result', [
    {'success': True, 'dataset_version': 'v2', 'rows': [], 'columns': {}, 'truncated': False},
    {'success': True, 'dataset_version': 'v1', 'rows': [{'x': 1}], 'columns': {}, 'truncated': False},
    {'success': True, 'dataset_version': 'v1', 'rows': [{'x': float('nan')}], 'columns': {'x': {'type': 'quantitative'}}, 'truncated': False},
])
def test_result_drift_rejected(tmp_path, result):
    # repr(nan) needs a bound name in the trusted test interface.
    path = custom(tmp_path, result=result)
    path.write_text('nan = float("nan")\n' + path.read_text(encoding='utf-8'), encoding='utf-8')
    ds = loader()(path, {})
    assert ds.execute('custom', {})['success'] is False
    ds.close()


def test_invalid_schema_and_duplicate_tools_rejected(tmp_path):
    with pytest.raises(ValueError):
        loader()(custom(tmp_path, schema={'type': 'not-a-type'}), {})
    with pytest.raises(ValueError):
        loader()(custom(tmp_path, duplicate=True), {})


def write_minimal_olist_csvs(tmp_path):
    fixtures = {
        'olist_orders_dataset.csv': 'order_id,customer_id,order_status,order_purchase_timestamp,order_approved_at,order_delivered_carrier_date,order_delivered_customer_date,order_estimated_delivery_date\no1,c1,delivered,2018-01-01,2018-01-01,2018-01-02,2018-01-03,2018-01-04\no2,c2,delivered,2018-01-02,2018-01-02,2018-01-03,2018-01-04,2018-01-05\no3,c2,canceled,2018-01-03,,,,2018-01-06\n',
        'olist_order_items_dataset.csv': 'order_id,order_item_id,product_id,seller_id,shipping_limit_date,price,freight_value\no1,1,p1,s1,2018-01-02,10,5\no1,2,p1,s1,2018-01-02,20,5\no2,1,p1,s1,2018-01-03,30,5\no3,1,p1,s1,2018-01-04,999,5\n',
        'olist_order_payments_dataset.csv': 'order_id,payment_sequential,payment_type,payment_installments,payment_value\no1,1,credit_card,1,40\no2,1,boleto,1,35\no3,1,credit_card,1,1004\n',
        'olist_order_reviews_dataset.csv': 'review_id,order_id,review_score,review_comment_title,review_comment_message,review_creation_date,review_answer_timestamp\nr1,o1,1,,,2018-01-03,2018-01-03\nr2,o1,5,,,2018-01-04,2018-01-04\nr3,o2,3,,,2018-01-04,2018-01-04\n',
        'olist_customers_dataset.csv': 'customer_id,customer_unique_id,customer_zip_code_prefix,customer_city,customer_state\nc1,u1,1000,sao paulo,SP\nc2,u2,2000,rio de janeiro,RJ\n',
        'olist_products_dataset.csv': 'product_id,product_category_name,product_name_lenght,product_description_lenght,product_photos_qty,product_weight_g,product_length_cm,product_height_cm,product_width_cm\np1,livros,10,100,1,1000,10,10,10\n',
        'olist_sellers_dataset.csv': 'seller_id,seller_zip_code_prefix,seller_city,seller_state\ns1,1000,sao paulo,SP\n',
        'olist_geolocation_dataset.csv': 'geolocation_zip_code_prefix,geolocation_lat,geolocation_lng,geolocation_city,geolocation_state\n1000,-23.5,-46.6,sao paulo,SP\n',
        'product_category_name_translation.csv': 'product_category_name,product_category_name_english\nlivros,books\n',
    }
    for name, body in fixtures.items():
        (tmp_path / name).write_text(body, encoding='utf-8')


def test_olist_order_grain_price_and_latest_review(tmp_path):
    write_minimal_olist_csvs(tmp_path)
    ds = loader()(ROOT / 'datasets/olist/interface.py', {'data_dir': str(tmp_path)})
    try:
        result = ds.execute('aggregate', {
            'group_by': ['product_category'],
            'metrics': ['order_count', 'revenue', 'avg_review_score'],
        })
        assert result['success'], result
        assert result['rows'] == [{
            'product_category': 'books', 'order_count': 2,
            'revenue': 60.0, 'avg_review_score': 4.0,
        }]
        scoped = ds.execute('aggregate', {
            'group_by': ['product_category'], 'metrics': ['order_count'],
        }, [{'field':'customer_state','op':'eq','value':'SP'}])
        assert scoped['rows'][0]['order_count'] == 1
        assert ds.description['validation']['order_grain_delivered_order_count'] == 2
    finally:
        ds.close()


def test_postponed_dataclass_module_lifetime(tmp_path):
    path = custom(tmp_path)
    path.write_text('from __future__ import annotations\nfrom dataclasses import dataclass\n@dataclass\nclass Record:\n    value: int\n' + path.read_text(encoding='utf-8'), encoding='utf-8')
    before = set(sys.modules)
    ds = loader()(path, {})
    added = {name for name in set(sys.modules) - before if name.startswith('trusted_dataset_')}
    assert len(added) == 1
    assert ds.execute('custom', {})['success']
    ds.close()
    assert not added.intersection(sys.modules)


def test_failed_load_removes_registered_module(tmp_path):
    path = custom(tmp_path, duplicate=True)
    before = {name for name in sys.modules if name.startswith('trusted_dataset_')}
    with pytest.raises(ValueError):
        loader()(path, {})
    assert {name for name in sys.modules if name.startswith('trusted_dataset_')} == before


@pytest.mark.parametrize('kind,value', [
    ('temporal', {'not': 'a date'}), ('temporal', ['2025-01-01']),
    ('temporal', True), ('temporal', 123), ('temporal', 'not-a-date'),
    ('nominal', {'nested': 1}), ('ordinal', [1, 2]),
])
def test_invalid_table_cells_rejected(tmp_path, kind, value):
    result = {'success': True, 'dataset_version': 'v1', 'rows': [{'x': value}],
              'columns': {'x': {'type': kind}}, 'truncated': False}
    ds = loader()(custom(tmp_path, result=result), {})
    try:
        response = ds.execute('custom', {})
        assert response['success'] is False
        assert response['error']['code'] == 'dataset_error'
    finally:
        ds.close()


@pytest.mark.parametrize('value', ['2025-01-01', '2025-01-01T12:34:56', '2025-01-01T12:34:56Z', None])
def test_iso_temporal_cells_accepted(tmp_path, value):
    result = {'success': True, 'dataset_version': 'v1', 'rows': [{'x': value}],
              'columns': {'x': {'type': 'temporal'}}, 'truncated': False}
    ds = loader()(custom(tmp_path, result=result), {})
    try:
        assert ds.execute('custom', {})['rows'] == [{'x': value}]
    finally:
        ds.close()


@pytest.mark.parametrize('expression,expected', [
    ('date(2025, 1, 1)', '2025-01-01'),
    ('datetime(2025, 1, 1, 12, 30)', '2025-01-01T12:30:00'),
])
def test_python_temporal_cells_normalized(tmp_path, expression, expected):
    result = {'success': True, 'dataset_version': 'v1', 'rows': [{'x': 'TEMPORAL_VALUE'}],
              'columns': {'x': {'type': 'temporal'}}, 'truncated': False}
    path = custom(tmp_path, result=result)
    path.write_text('from datetime import date, datetime\n' + path.read_text(encoding='utf-8').replace("'TEMPORAL_VALUE'", expression), encoding='utf-8')
    ds = loader()(path, {})
    try:
        assert ds.execute('custom', {})['rows'] == [{'x': expected}]
    finally:
        ds.close()


def test_import_failure_removes_registered_module(tmp_path):
    path = custom(tmp_path)
    path.write_text('raise RuntimeError("bad interface")\n', encoding='utf-8')
    before = {name for name in sys.modules if name.startswith('trusted_dataset_')}
    with pytest.raises(RuntimeError, match='bad interface'):
        loader()(path, {})
    assert {name for name in sys.modules if name.startswith('trusted_dataset_')} == before
