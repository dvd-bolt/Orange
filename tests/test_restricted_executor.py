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
