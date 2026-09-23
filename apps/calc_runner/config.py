"""Loads and validates the config-driven execution plan for calc_runner.

Reimplements report-transformation-service's `db_func_config.csv` idea: which DB functions run,
in what order, and whether they run sequentially (`S`) or can run in parallel (`P`) is DATA, not
code - an ops change to "add a new calculation" or "reorder two calculations" is a CSV edit (and,
in production, an S3 upload), not a Lambda redeploy.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List

VALID_TYPES = {'S', 'P'}

DEFAULT_CONFIG_PATH = Path(__file__).parent / 'db_func_config.csv'


class InvalidFunctionConfigError(Exception):
    """Raised when db_func_config.csv contains a row this runner can't act on safely."""


@dataclass(frozen=True)
class FunctionConfig:
    function_name: str
    type: str  # 'S' (sequential) or 'P' (parallel)
    order: int


def load_function_config(config_path: Path = DEFAULT_CONFIG_PATH) -> List[FunctionConfig]:
    with open(config_path, newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        configs = []
        for row in reader:
            function_type = row['type'].strip().upper()
            if function_type not in VALID_TYPES:
                raise InvalidFunctionConfigError(
                    f"{row['function_name']}: type must be one of {sorted(VALID_TYPES)}, got {row['type']!r}"
                )
            configs.append(
                FunctionConfig(
                    function_name=row['function_name'].strip(),
                    type=function_type,
                    order=int(row['order']),
                )
            )
        return configs


def sequential(configs: List[FunctionConfig]) -> List[FunctionConfig]:
    """Sequential functions, sorted by `order` - these always run first, one at a time."""
    return sorted((c for c in configs if c.type == 'S'), key=lambda c: c.order)


def parallel(configs: List[FunctionConfig]) -> List[FunctionConfig]:
    """Parallel functions - these all run concurrently, AFTER every sequential function has run.

    Note this mirrors the real service exactly: `order` on a parallel-typed row has no effect on
    execution order (see apps/calc_runner/README note in the training README's exercises) - it's
    purely informational unless you change the runner to group by it.
    """
    return [c for c in configs if c.type == 'P']
