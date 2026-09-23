from pathlib import Path

import pytest

from apps.calc_runner.config import (
    FunctionConfig,
    InvalidFunctionConfigError,
    load_function_config,
    parallel,
    sequential,
)

CONFIG_PATH = Path(__file__).parent.parent / 'apps' / 'calc_runner' / 'db_func_config.csv'


def test_loads_the_real_config_file():
    configs = load_function_config(CONFIG_PATH)
    assert configs == [
        FunctionConfig('calc_line_item_total', 'S', 1),
        FunctionConfig('calc_discount_total', 'P', 2),
        FunctionConfig('calc_tax_total', 'P', 2),
    ]


def test_sequential_returns_only_s_rows_sorted_by_order():
    configs = [
        FunctionConfig('b', 'S', 2),
        FunctionConfig('a', 'S', 1),
        FunctionConfig('c', 'P', 1),
    ]
    assert [c.function_name for c in sequential(configs)] == ['a', 'b']


def test_parallel_returns_only_p_rows():
    configs = [
        FunctionConfig('a', 'S', 1),
        FunctionConfig('b', 'P', 2),
        FunctionConfig('c', 'P', 2),
    ]
    assert {c.function_name for c in parallel(configs)} == {'b', 'c'}


def test_rejects_an_unrecognized_type(tmp_path):
    bad_csv = tmp_path / 'bad.csv'
    bad_csv.write_text("function_name,type,order\ncalc_something,X,1\n")

    with pytest.raises(InvalidFunctionConfigError):
        load_function_config(bad_csv)
