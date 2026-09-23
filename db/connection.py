"""Environment-driven DB connection helper.

Mirrors the real service's pattern of pulling `spring.datasource.url`/`username`/`password` from
SSM Parameter Store + Secrets Manager at runtime (see report-transformation-service's
.gitlab-ci.yml `liquibase_template` and the Lambda's `PARAMETER_STORE_APP_BASE_URL` env var) -
credentials and connection details come from the environment, never hardcoded, so the same code
runs unmodified against dev/stage/prod. For this training repo, sqlite3 stands in for a real
network database so the whole thing runs with zero external services.
"""
from __future__ import annotations

import os
import sqlite3


def get_connection(db_path: str = None) -> sqlite3.Connection:
    """Open a connection to the environment's database.

    `DB_PATH` (or the explicit `db_path` argument) stands in for what would otherwise be a
    `DATABASE_URL` pulled from SSM/Secrets Manager - `:memory:` by default so tests and local runs
    need no setup at all.
    """
    path = db_path or os.environ.get('DB_PATH', ':memory:')
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.execute('PRAGMA foreign_keys = ON')
    return connection
