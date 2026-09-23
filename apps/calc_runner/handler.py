"""The SQS-triggered handler: one invocation per batch of SQS records, each record naming one
order whose derived totals need (re)calculating.

Reimplements DbFunctionHandler.handleRequest from report-transformation-service: read the
config-driven execution plan, run every sequential function in order, then run every parallel
function concurrently, all before committing - and notify the caller either way. Unlike the real
service (which commits after every individual sequential function AND again at the end - not
fully atomic), this version commits exactly once, after everything succeeds, or rolls back
everything on any failure. See the README's exercises for why that distinction matters.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Optional

from apps.calc_runner.config import DEFAULT_CONFIG_PATH, load_function_config, parallel, sequential
from apps.calc_runner.functions import FUNCTION_REGISTRY, FunctionCallable
from apps.calc_runner.notifier import notify_completed


class UnknownFunctionError(Exception):
    """Raised when db_func_config.csv names a function this handler has no implementation for."""


def _run_sequential(connection: sqlite3.Connection, order_id: str, functions, registry) -> None:
    for function_config in functions:
        callable_fn = _resolve(function_config.function_name, registry)
        callable_fn(connection, order_id)


def _run_parallel(connection: sqlite3.Connection, order_id: str, functions, registry) -> None:
    if not functions:
        return

    # The real service shares one JDBC connection across CompletableFutures running
    # concurrently - not actually thread-safe for a real network DB driver either. This lock
    # reproduces that same "parallel dispatch, serialized actual DB access" shape rather than
    # hiding the issue - see the README's exercises for how you'd fix it for real (one
    # connection/transaction per worker). (sqlite3 additionally requires `check_same_thread=False`
    # for a connection to be touched from worker threads at all - see db/connection.py.)
    write_lock = threading.Lock()

    def run_one(function_config) -> None:
        callable_fn = _resolve(function_config.function_name, registry)
        with write_lock:
            callable_fn(connection, order_id)

    with ThreadPoolExecutor(max_workers=len(functions)) as executor:
        futures = [executor.submit(run_one, fc) for fc in functions]
        for future in as_completed(futures):
            future.result()  # re-raises any exception from the worker thread


def _resolve(function_name: str, registry) -> FunctionCallable:
    try:
        return registry[function_name]
    except KeyError:
        raise UnknownFunctionError(f"No implementation registered for db function {function_name!r}") from None


def process_order(
    order_id: str,
    connection: sqlite3.Connection,
    config_path: Path = DEFAULT_CONFIG_PATH,
    registry: Dict[str, FunctionCallable] = None,
    publish: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run every configured calc function for one order, inside a single transaction."""
    registry = registry if registry is not None else FUNCTION_REGISTRY
    configs = load_function_config(config_path)

    try:
        _run_sequential(connection, order_id, sequential(configs), registry)
        _run_parallel(connection, order_id, parallel(configs), registry)
        connection.commit()
    except Exception as exc:
        connection.rollback()
        if publish is not None:
            notify_completed(order_id, publish, error=str(exc))
        raise

    if publish is not None:
        notify_completed(order_id, publish)
    return {'orderId': order_id, 'status': 'SUCCESS'}


def handler(
    event: Dict[str, Any],
    _context: Any = None,
    connection: sqlite3.Connection = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
    registry: Dict[str, FunctionCallable] = None,
    publish: Optional[Any] = None,
) -> Dict[str, Any]:
    """SQS event handler - `event['Records']` is a batch of `{"body": "...json..."}` messages."""
    results = []
    for record in event['Records']:
        body = json.loads(record['body'])
        order_id = body['orderId']
        results.append(
            process_order(order_id, connection, config_path=config_path, registry=registry, publish=publish)
        )
    return {'processed': results}
