from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from wepositive_di.di import Depends, clear_overrides, inject, register_provider, setup


@pytest.fixture
def mock_config(mocker: MockerFixture) -> MagicMock:
    mock_cfg = mocker.MagicMock()
    mock_cfg.api_url = "https://api.example.com"
    mock_cfg.timeout = 30
    return mock_cfg


async def test_async_function_provider_with_dependency(
    mock_config: MagicMock,
) -> None:
    @register_provider()
    async def base_config() -> MagicMock:
        return mock_config

    @register_provider()
    async def api_client(cfg: Any = Depends[base_config]) -> dict[str, Any]:
        return {"url": cfg.api_url, "timeout": cfg.timeout}

    @inject
    async def get_client(client: Any = Depends[api_client]) -> Any:
        return client

    setup()

    result = await get_client()

    assert result["url"] == "https://api.example.com"
    assert result["timeout"] == 30


async def test_multiple_chained_async_provider_dependencies() -> None:
    @register_provider()
    async def config_provider() -> dict[str, str]:
        return {"db_host": "localhost"}

    @register_provider()
    async def connection_provider(
        cfg: Any = Depends[config_provider],
    ) -> dict[str, str]:
        return {"host": cfg["db_host"]}

    @register_provider()
    async def session_provider(
        conn: Any = Depends[connection_provider],
    ) -> dict[str, Any]:
        return {"connection": conn, "data": ["data"]}

    @inject
    async def get_data(session: Any = Depends[session_provider]) -> list[str]:
        return session["data"]

    setup()

    assert await get_data() == ["data"]


async def test_async_provider_with_multiple_dependencies() -> None:
    @register_provider()
    async def auth_provider() -> dict[str, str]:
        return {"token": "secret_token"}

    @register_provider()
    async def config_provider() -> dict[str, str]:
        return {"api_url": "https://api.example.com"}

    @register_provider()
    async def api_client_provider(
        auth: Any = Depends[auth_provider], cfg: Any = Depends[config_provider]
    ) -> dict[str, str]:
        return {"url": cfg["api_url"], "token": auth["token"]}

    @inject
    async def make_request(
        client: Any = Depends[api_client_provider],
    ) -> dict[str, str]:
        return client

    setup()

    result = await make_request()

    assert result["url"] == "https://api.example.com"
    assert result["token"] == "secret_token"


async def test_async_function_provider_resolves_internal_dependencies() -> None:
    @register_provider()
    async def base_config() -> dict[str, Any]:
        return {"multiplier": 5}

    @register_provider()
    async def computed_value(cfg: dict[str, Any] = Depends[base_config]) -> int:
        return cfg["multiplier"] * 10

    @inject
    async def consumer(value: int = Depends[computed_value]) -> int:
        return value

    assert await consumer() == 50
    clear_overrides()


async def test_async_func_with_multiple_dependencies() -> None:
    @register_provider()
    async def dep1() -> int:
        return 5

    @register_provider()
    async def dep2() -> int:
        return 15

    @register_provider()
    async def func_with_multiple_deps(
        val1: int = Depends[dep1], val2: int = Depends[dep2]
    ) -> int:
        return val1 * val2

    @inject
    async def consumer(value: int = Depends[func_with_multiple_deps]) -> int:
        return value

    assert await consumer() == 75
    clear_overrides()


async def test_async_func_provider_with_non_depends_param() -> None:
    @register_provider()
    async def base() -> int:
        return 4

    @register_provider()
    async def func_mixed(
        multiplier: int = 10,
        val: int = Depends[base],
    ) -> int:
        return val * multiplier

    @inject
    async def consumer(result: int = Depends[func_mixed]) -> int:
        return result

    assert await consumer() == 40
    clear_overrides()


async def test_inject_async_func_with_non_depends_param() -> None:
    @register_provider()
    async def dep() -> int:
        return 10

    @inject
    async def consumer(
        x: int = 5,
        val: int = Depends[dep],
    ) -> int:
        return x + val

    assert await consumer() == 15
    clear_overrides()


async def test_async_func_depends_on_sync_provider() -> None:
    @register_provider()
    def sync_base() -> str:
        return "world"

    @register_provider()
    async def func_with_sync_dep(label: str = Depends[sync_base]) -> str:
        return f"hello {label}"

    @inject
    async def consumer(result: str = Depends[func_with_sync_dep]) -> str:
        return result

    assert await consumer() == "hello world"
    clear_overrides()


async def test_provider_returns_callable_with_own_dependencies() -> None:
    @register_provider()
    async def multiplier() -> int:
        return 3

    @register_provider()
    async def make_multiply(factor: int = Depends[multiplier]) -> Callable[[int], int]:
        def multiply(value: int) -> int:
            return value * factor

        return multiply

    @inject
    async def consumer(fn: Callable[[int], int] = Depends[make_multiply]) -> int:
        return fn(7)

    setup()
    try:
        assert await consumer() == 21
    finally:
        clear_overrides()


async def test_async_function_with_async_dependency_coroutine_resolution() -> None:
    @register_provider()
    async def async_dep() -> int:
        return 555

    @register_provider()
    async def func_with_async_dep(val: int = Depends[async_dep]) -> int:
        return val * 3

    @inject
    async def consumer(value: int = Depends[func_with_async_dep]) -> int:
        return value

    assert await consumer() == 1665
    clear_overrides()


async def test_async_dependency_exception_propagates_through_chain() -> None:
    @register_provider()
    async def failing_provider() -> Any:
        raise ValueError("Provider failed")

    @inject
    async def function_with_failing_dep(val: Any = Depends[failing_provider]) -> Any:
        return val

    setup()

    with pytest.raises(ValueError, match="Provider failed"):
        await function_with_failing_dep()
