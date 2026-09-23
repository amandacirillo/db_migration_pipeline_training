import sqlite3
from pathlib import Path

import pytest

from db.migration_runner import ChecksumMismatchError, MigrationRunner, load_changelog

CHANGELOG_DIR = Path(__file__).parent.parent / 'migrations' / 'changelog'


def new_connection() -> sqlite3.Connection:
    return sqlite3.connect(':memory:')


def test_load_changelog_reads_files_in_numeric_order():
    changesets = load_changelog(CHANGELOG_DIR)
    assert [c.filename for c in changesets] == [
        '001_create_orders_table.sql',
        '002_create_order_totals_table.sql',
        '003_seed_dev_sample_data.sql',
        '004_add_currency_to_order_totals.sql',
    ]


def test_load_changelog_parses_context_headers():
    changesets = load_changelog(CHANGELOG_DIR)
    by_name = {c.filename: c for c in changesets}
    assert by_name['001_create_orders_table.sql'].contexts == ['ALL']
    assert by_name['003_seed_dev_sample_data.sql'].contexts == ['DEV', 'STAGE']


def test_prod_context_skips_dev_only_seed_data():
    connection = new_connection()
    changesets = load_changelog(CHANGELOG_DIR)
    runner = MigrationRunner(connection, context='PROD')

    applied = runner.run(changesets)

    assert '003_seed_dev_sample_data.sql' not in applied
    row_count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    assert row_count == 0


def test_dev_context_applies_seed_data():
    connection = new_connection()
    changesets = load_changelog(CHANGELOG_DIR)
    runner = MigrationRunner(connection, context='DEV')

    applied = runner.run(changesets)

    assert '003_seed_dev_sample_data.sql' in applied
    row_count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    assert row_count == 2


def test_running_twice_is_idempotent():
    connection = new_connection()
    changesets = load_changelog(CHANGELOG_DIR)
    runner = MigrationRunner(connection, context='DEV')

    first_run = runner.run(changesets)
    second_run = runner.run(changesets)

    assert len(first_run) == 4
    assert second_run == []


def test_editing_an_applied_changeset_raises_checksum_mismatch():
    connection = new_connection()
    changesets = load_changelog(CHANGELOG_DIR)
    runner = MigrationRunner(connection, context='ALL')
    runner.run(changesets)

    tampered = changesets[0]
    tampered_changesets = list(changesets)
    tampered_changesets[0] = tampered.__class__(
        order=tampered.order,
        filename=tampered.filename,
        contexts=tampered.contexts,
        sql=tampered.sql + "\n-- sneaky edit",
        checksum='deadbeef-not-the-real-checksum',
    )

    with pytest.raises(ChecksumMismatchError):
        runner.run(tampered_changesets)
