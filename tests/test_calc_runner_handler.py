import json
import sqlite3
from pathlib import Path

import pytest

from apps.calc_runner.handler import UnknownFunctionError, handler, process_order
from db.migration_runner import MigrationRunner, load_changelog

CHANGELOG_DIR = Path(__file__).parent.parent / 'migrations' / 'changelog'
CONFIG_PATH = Path(__file__).parent.parent / 'apps' / 'calc_runner' / 'db_func_config.csv'


@pytest.fixture()
def connection():
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    MigrationRunner(conn, context='ALL').run(load_changelog(CHANGELOG_DIR))
    conn.execute("INSERT INTO orders (order_id, program_code) VALUES ('order-1', 'DEMO')")
    conn.commit()
    yield conn
    conn.close()


def test_process_order_runs_sequential_then_parallel_functions(connection):
    published = []

    result = process_order('order-1', connection, config_path=CONFIG_PATH, publish=published.append)

    assert result == {'orderId': 'order-1', 'status': 'SUCCESS'}
    row = connection.execute(
        "SELECT line_item_total, discount_total, tax_total FROM order_totals WHERE order_id = 'order-1'"
    ).fetchone()
    assert row == (100.0, 10.0, 7.5)
    assert published == [{'orderId': 'order-1', 'status': 'SUCCESS', 'error': None}]


def test_process_order_rolls_back_and_notifies_failure_on_unknown_function(connection, tmp_path):
    bad_config = tmp_path / 'bad_func_config.csv'
    bad_config.write_text("function_name,type,order\ncalc_line_item_total,S,1\ncalc_does_not_exist,P,2\n")
    published = []

    with pytest.raises(UnknownFunctionError):
        process_order('order-1', connection, config_path=bad_config, publish=published.append)

    # calc_line_item_total ran (S phase succeeded) but the whole transaction rolled back because
    # calc_does_not_exist failed in the P phase - nothing should have been persisted.
    row = connection.execute(
        "SELECT line_item_total FROM order_totals WHERE order_id = 'order-1'"
    ).fetchone()
    assert row is None
    assert published == [{'orderId': 'order-1', 'status': 'FAILED', 'error': "No implementation registered for db function 'calc_does_not_exist'"}]


def test_handler_processes_every_sqs_record(connection):
    connection.execute("INSERT INTO orders (order_id, program_code) VALUES ('order-2', 'DEMO')")
    connection.commit()

    event = {
        'Records': [
            {'body': json.dumps({'orderId': 'order-1'})},
            {'body': json.dumps({'orderId': 'order-2'})},
        ]
    }

    result = handler(event, connection=connection, config_path=CONFIG_PATH)

    assert result == {
        'processed': [
            {'orderId': 'order-1', 'status': 'SUCCESS'},
            {'orderId': 'order-2', 'status': 'SUCCESS'},
        ]
    }
