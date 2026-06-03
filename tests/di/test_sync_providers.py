import concurrent.futures
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from wepositive_di.di import Depends, clear_overrides, inject, register_provider, setup


@pytest.fixture
def mock_config(mocker: MockerFixture) -> MagicMock:
    config = mocker.MagicMock()
    config.value = "test_config"
    return config


def test_sync_provider_with_sync_dependency(mocker: MockerFixture) -> None:
    @register_provider()
    def base_value() -> int:
        return 42

    @register_provider()
    def derived_value(base: Any = Depends[base_value]) -> int:
        return base * 2

    @inject
    def get_value(val: Any = Depends[derived_value]) -> int:
        return val

    setup()

    assert get_value() == 84
    _ = mocker


def test_sync_function_provider_resolves_internal_dependencies() -> None:
    @register_provider()
    def base_config() -> dict[str, Any]:
        return {"multiplier": 7}

    @register_provider()
    def computed_value(cfg: dict[str, Any] = Depends[base_config]) -> int:
        return cfg["multiplier"] * 10

    @inject
    def consumer(value: int = Depends[computed_value]) -> int:
        return value

    assert consumer() == 70
    clear_overrides()


def test_sync_func_provider_with_non_depends_param() -> None:
    @register_provider()
    def base() -> int:
        return 9

    @register_provider()
    def func_mixed(
        multiplier: int = 5,
        val: int = Depends[base],
    ) -> int:
        return val * multiplier

    @inject
    def consumer(result: int = Depends[func_mixed]) -> int:
        return result

    assert consumer() == 45
    clear_overrides()


def test_inject_sync_func_with_non_depends_param() -> None:
    @register_provider()
    def dep() -> int:
        return 20

    @inject
    def consumer(
        x: int = 3,
        val: int = Depends[dep],
    ) -> int:
        return x + val

    assert consumer() == 23
    clear_overrides()


def test_inject_on_decorator() -> None:
    @register_provider()
    def prefix_provider() -> str:
        return "hello"

    @inject
    def add_prefix(
        func: Callable[..., str], prefix: str = Depends[prefix_provider]
    ) -> Callable[..., str]:
        def wrapper(*args: Any, **kwargs: Any) -> str:
            return f"{prefix}_{func(*args, **kwargs)}"

        return wrapper

    @add_prefix
    def greet(name: str) -> str:
        return name

    assert greet("world") == "hello_world"
    clear_overrides()


def test_sync_provider_with_async_dependency_errors_without_event_loop(
    mock_config: MagicMock,
) -> None:
    @register_provider()
    async def async_config() -> Any:
        return mock_config

    @register_provider()
    def sync_provider_needs_async(cfg: Any = Depends[async_config]) -> Any:
        return cfg.value

    @inject
    def use_sync_provider(value: Any = Depends[sync_provider_needs_async]) -> Any:
        return value

    setup()

    with pytest.raises(RuntimeError, match="Sync providers cannot have async dependencies"):
        use_sync_provider()  # pyright: ignore[reportUnusedCoroutine]


async def test_sync_provider_with_async_dependency_errors_inside_event_loop(
    mock_config: MagicMock,
) -> None:
    @register_provider()
    async def async_config() -> Any:
        return mock_config

    @register_provider()
    def sync_provider_needs_async(cfg: Any = Depends[async_config]) -> Any:
        return cfg.value

    @inject
    async def use_sync_provider(value: Any = Depends[sync_provider_needs_async]) -> Any:
        return value

    setup()

    with pytest.raises(RuntimeError, match="Sync providers cannot have async dependencies"):
        await use_sync_provider()


async def test_sync_function_with_async_dependency_errors_inside_event_loop() -> None:
    @register_provider()
    async def async_dep() -> str:
        return "async_value"

    @inject
    def sync_func_with_async_dep(val: Any = Depends[async_dep]) -> Any:
        return val

    with pytest.raises(RuntimeError, match="from within an async context"):
        sync_func_with_async_dep()  # pyright: ignore[reportUnusedCoroutine]


async def test_sync_provider_with_async_dependency_errors_outside_event_loop() -> None:
    @register_provider()
    async def async_dep() -> int:
        return 999

    @register_provider()
    def sync_func_with_async_dep(val: int = Depends[async_dep]) -> int:
        return val * 2

    def run_in_thread() -> None:
        @inject
        def consumer(value: int = Depends[sync_func_with_async_dep]) -> int:
            return value

        with pytest.raises(RuntimeError, match="Cannot resolve async dependency"):
            consumer()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.submit(run_in_thread).result()

    clear_overrides()


def test_inject_sync_func_with_async_dep_no_event_loop() -> None:
    @register_provider()
    async def async_dep() -> int:
        return 888

    @inject
    def sync_consumer(value: int = Depends[async_dep]) -> int:
        return value * 2

    result_container: list[int] = []

    def call_in_thread() -> None:
        result_container.append(sync_consumer())

    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.submit(call_in_thread).result()

    assert result_container == [888 * 2]
    clear_overrides()
