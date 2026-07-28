import asyncio

import pytest


def test_restricted_executor_allows_simple_code():
    pytest.importorskip("pydantic_ai")
    from core.tools import validate_python_for_restricted_executor

    validate_python_for_restricted_executor("import math\nprint(math.sqrt(16))")


def test_restricted_executor_rejects_os_import():
    pytest.importorskip("pydantic_ai")
    from core.tools import validate_python_for_restricted_executor

    with pytest.raises(ValueError):
        validate_python_for_restricted_executor("import os\nprint(os.getcwd())")


def test_restricted_executor_rejects_absolute_user_path():
    pytest.importorskip("pydantic_ai")
    from core.tools import validate_python_for_restricted_executor

    with pytest.raises(ValueError):
        validate_python_for_restricted_executor("print('/Users/example/secret.txt')")


@pytest.mark.parametrize(
    "path",
    [
        "/home/user/secret.txt",
        "../../secret.txt",
        r"C:\Users\user\secret.txt",
        r"\\server\share\secret.txt",
    ],
)
def test_restricted_executor_rejects_cross_platform_paths(path):
    from core.tools import validate_python_for_restricted_executor

    with pytest.raises(ValueError):
        validate_python_for_restricted_executor(f"print({path!r})")


def test_restricted_executor_runs_whitelisted_standard_library_modules():
    from core.tools import execute_python_restricted

    async def approve(_command):
        return True

    code = (
        "import collections, datetime, decimal, fractions, itertools, json, math, random, re, statistics\n"
        "values = [math.sqrt(16), statistics.mean([2, 4]), fractions.Fraction(1, 2)]\n"
        "print(json.dumps([str(value) for value in values]))"
    )
    result = asyncio.run(execute_python_restricted(code, approve))

    assert result.startswith("=== EXECUTION RESULT")
    assert '\"4.0\"' in result


def test_restricted_executor_bootstrap_installs_runtime_audit_guards():
    from core.tools import _executor_bootstrap

    bootstrap = _executor_bootstrap()
    assert "sys.addaudithook(_audit)" in bootstrap
    assert "socket." in bootstrap
    assert "Restricted executor blocked file access" in bootstrap
