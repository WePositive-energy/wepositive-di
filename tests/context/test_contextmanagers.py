"""Tests for generator dependencies and cleanup."""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from wepositive_di.di import (
    Depends,
    clear_overrides,
    inject,
    register_provider,
    registry,
    setup,
)


@pytest.fixture
def cleanup_tracker(mocker: MockerFixture) -> MagicMock:
    """Track cleanup calls for testing generator lifecycle."""
    tracker = mocker.MagicMock()
    tracker.async_gen_cleanup = mocker.AsyncMock()
    tracker.sync_gen_cleanup = mocker.MagicMock()
    tracker.exception_handler = mocker.MagicMock()
    return tracker


@pytest.mark.skip_wire
async def test_async_generator_dependency_in_async_function(
    mocker: MockerFixture, cleanup_tracker: MagicMock
) -> None:
    """Test async CM provider as dependency in async function."""
    from contextlib import asynccontextmanager

    @register_provider(context_manager=True)
    @asynccontextmanager
    async def async_session_provider() -> AsyncGenerator[MagicMock, None]:
        session = mocker.MagicMock()
        session.query = mocker.AsyncMock(return_value=["data"])
        yield session
        await cleanup_tracker.async_gen_cleanup()

    @inject
    async def query_database(session: Any = Depends[async_session_provider]) -> Any:
        return await session.query()

    setup()

    result = await query_database()

    assert result == ["data"]
    cleanup_tracker.async_gen_cleanup.assert_awaited_once()


@pytest.mark.skip_wire
async def test_sync_generator_dependency_in_async_function(
    mocker: MockerFixture, cleanup_tracker: MagicMock
) -> None:
    """Test sync CM provider as dependency in async function."""
    from contextlib import contextmanager

    @register_provider(context_manager=True)
    @contextmanager
    def sync_resource_provider() -> Generator[MagicMock, None, None]:
        resource = mocker.MagicMock()
        resource.value = "resource_data"
        yield resource
        cleanup_tracker.sync_gen_cleanup()

    @inject
    async def use_resource(resource: Any = Depends[sync_resource_provider]) -> str:
        return resource.value

    setup()

    result = await use_resource()

    assert result == "resource_data"
    cleanup_tracker.sync_gen_cleanup.assert_called_once()


@pytest.mark.skip_wire
def test_sync_generator_dependency_in_sync_function(
    mocker: MockerFixture, cleanup_tracker: MagicMock
) -> None:
    """Test sync CM provider as dependency in sync function."""
    from contextlib import contextmanager

    @register_provider(context_manager=True)
    @contextmanager
    def file_provider() -> Generator[MagicMock, None, None]:
        file_handle = mocker.MagicMock()
        file_handle.read = mocker.MagicMock(return_value="file_content")
        yield file_handle
        cleanup_tracker.sync_gen_cleanup()

    @inject
    def read_file(file: Any = Depends[file_provider]) -> str:
        return file.read()

    setup()

    result = read_file()

    assert result == "file_content"
    cleanup_tracker.sync_gen_cleanup.assert_called_once()


@pytest.mark.skip_wire
def test_async_generator_dependency_in_sync_function(
    mocker: MockerFixture, cleanup_tracker: MagicMock
) -> None:
    """Test async CM provider as dependency in sync function (sync context).

    Runs in a thread to simulate a true sync context (no event loop).
    """
    import threading
    from contextlib import asynccontextmanager

    @register_provider(context_manager=True)
    @asynccontextmanager
    async def async_session_provider() -> AsyncGenerator[MagicMock, None]:
        session = mocker.MagicMock()
        session.query = mocker.MagicMock(return_value="async_query_result")
        try:
            yield session
        finally:
            await cleanup_tracker.async_gen_cleanup()

    @inject
    def query_database(session: Any = Depends[async_session_provider]) -> str:
        return session.query()

    setup()

    result_container: list[str] = []
    error_container: list[Exception] = []

    def run_test():
        try:
            result = query_database()
            result_container.append(result)
        except Exception as e:  # noqa: BLE001
            error_container.append(e)

    thread = threading.Thread(target=run_test)
    thread.start()
    thread.join()

    if error_container:
        raise error_container[0]

    assert len(result_container) == 1
    assert result_container[0] == "async_query_result"
    cleanup_tracker.async_gen_cleanup.assert_called_once()


@pytest.mark.skip_wire
def test_async_coroutine_dependency_in_sync_function() -> None:
    """Test async coroutine (regular async function) as dependency in sync function (sync context).

    This test runs in a thread to simulate a true sync context (no event loop).
    """
    import threading

    call_count = 0

    @register_provider()
    async def async_config_provider() -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {
            "api_url": "https://api.example.com",
            "timeout": 30,
            "call_count": call_count,
        }

    @inject
    def get_api_url(config: dict[str, Any] = Depends[async_config_provider]) -> str:
        return config["api_url"]

    setup()

    result_container: list[str] = []
    error_container: list[Exception] = []

    def run_test():
        try:
            result = get_api_url()
            result_container.append(result)
        except Exception as e:  # noqa: BLE001
            error_container.append(e)

    thread = threading.Thread(target=run_test)
    thread.start()
    thread.join()

    if error_container:
        raise error_container[0]

    assert len(result_container) == 1
    assert result_container[0] == "https://api.example.com"
    assert call_count == 1


@pytest.mark.skip_wire
async def test_async_dependency_in_sync_function_from_async_context_errors() -> None:
    """Test that sync functions with async dependencies error when called from async context."""

    @register_provider()
    async def async_config_provider() -> dict[str, Any]:
        return {"api_url": "https://api.example.com"}

    @inject
    def sync_func_with_async_dep(
        config: dict[str, Any] = Depends[async_config_provider],
    ) -> str:
        return config["api_url"]

    setup()

    with pytest.raises(
        RuntimeError,
        match=r"Cannot resolve async dependency 'config' in sync function 'sync_func_with_async_dep' from within an async context",
    ):
        sync_func_with_async_dep()


@pytest.mark.skip_wire
async def test_async_generator_in_sync_function_from_async_context_errors(
    mocker: MockerFixture,
) -> None:
    """Test that sync functions with async CM dependencies error when called from async context."""
    from contextlib import asynccontextmanager

    @register_provider(context_manager=True)
    @asynccontextmanager
    async def async_session_provider() -> AsyncGenerator[MagicMock, None]:
        session = mocker.MagicMock()
        yield session

    @inject
    def sync_func_with_async_gen(session: Any = Depends[async_session_provider]) -> Any:
        return session

    setup()

    with pytest.raises(
        RuntimeError,
        match=r"Cannot resolve async dependency 'session' in sync function 'sync_func_with_async_gen' from within an async context",
    ):
        sync_func_with_async_gen()  # type: ignore[reportUnusedCoroutine]


@pytest.mark.skip_wire
async def test_async_generator_cleanup_with_exception(
    mocker: MockerFixture, cleanup_tracker: MagicMock
) -> None:
    """Test async CM cleanup when exception occurs in function."""
    from contextlib import asynccontextmanager

    @register_provider(context_manager=True)
    @asynccontextmanager
    async def session_provider() -> AsyncGenerator[MagicMock, None]:
        session = mocker.MagicMock()
        try:
            yield session
        finally:
            await cleanup_tracker.async_gen_cleanup()

    @inject
    async def failing_function(session: Any = Depends[session_provider]) -> None:
        raise ValueError("Something went wrong")

    setup()

    with pytest.raises(ValueError, match="Something went wrong"):
        await failing_function()

    cleanup_tracker.async_gen_cleanup.assert_awaited_once()


@pytest.mark.skip_wire
async def test_sync_generator_cleanup_with_exception_in_async(
    mocker: MockerFixture, cleanup_tracker: MagicMock
) -> None:
    """Test sync CM cleanup when exception occurs in async function."""
    from contextlib import contextmanager

    @register_provider(context_manager=True)
    @contextmanager
    def resource_provider() -> Generator[MagicMock, None, None]:
        resource = mocker.MagicMock()
        try:
            yield resource
        finally:
            cleanup_tracker.sync_gen_cleanup()

    @inject
    async def failing_function(resource: Any = Depends[resource_provider]) -> None:
        raise RuntimeError("Async function failed")

    setup()

    with pytest.raises(RuntimeError, match="Async function failed"):
        await failing_function()

    cleanup_tracker.sync_gen_cleanup.assert_called_once()


@pytest.mark.skip_wire
def test_sync_generator_cleanup_with_exception_in_sync(
    mocker: MockerFixture, cleanup_tracker: MagicMock
) -> None:
    """Test sync CM cleanup when exception occurs in sync function."""
    from contextlib import contextmanager

    @register_provider(context_manager=True)
    @contextmanager
    def connection_provider() -> Generator[MagicMock, None, None]:
        conn = mocker.MagicMock()
        try:
            yield conn
        finally:
            cleanup_tracker.sync_gen_cleanup()

    @inject
    def failing_function(conn: Any = Depends[connection_provider]) -> None:
        raise OSError("Sync function failed")

    setup()

    with pytest.raises(IOError, match="Sync function failed"):
        failing_function()

    cleanup_tracker.sync_gen_cleanup.assert_called_once()


@pytest.mark.skip_wire
async def test_multiple_generators_cleanup_in_order(
    mocker: MockerFixture, cleanup_tracker: MagicMock
) -> None:
    """Test that multiple CM dependencies are cleaned up."""
    from contextlib import asynccontextmanager

    cleanup_order: list[str] = []

    @register_provider(context_manager=True)
    @asynccontextmanager
    async def first_provider() -> AsyncGenerator[MagicMock, None]:
        resource = mocker.MagicMock()
        resource.name = "first"
        yield resource
        cleanup_order.append("first")
        await cleanup_tracker.async_gen_cleanup()

    @register_provider(context_manager=True)
    @asynccontextmanager
    async def second_provider() -> AsyncGenerator[MagicMock, None]:
        resource = mocker.MagicMock()
        resource.name = "second"
        yield resource
        cleanup_order.append("second")
        await cleanup_tracker.async_gen_cleanup()

    @inject
    async def use_both(
        first: Any = Depends[first_provider], second: Any = Depends[second_provider]
    ) -> str:
        return f"{first.name}-{second.name}"

    setup()

    result = await use_both()

    assert result == "first-second"
    assert len(cleanup_order) == 2
    assert cleanup_tracker.async_gen_cleanup.await_count == 2


@pytest.mark.skip_wire
async def test_async_generator_cleanup_handles_exception_in_cleanup(
    mocker: MockerFixture, cleanup_tracker: MagicMock
) -> None:
    """Test that exceptions during CM cleanup propagate to the caller.

    With the CM-based system, exceptions raised in cleanup code propagate
    out of the context manager's __aexit__ and replace the body exception.
    """
    from contextlib import asynccontextmanager

    async def cleanup_that_fails() -> None:
        raise RuntimeError("Cleanup failed")

    @register_provider(context_manager=True)
    @asynccontextmanager
    async def provider_with_failing_cleanup() -> AsyncGenerator[MagicMock, None]:
        resource = mocker.MagicMock()
        yield resource
        await cleanup_that_fails()

    @inject
    async def use_resource(
        resource: Any = Depends[provider_with_failing_cleanup],
    ) -> str:
        return "success"

    setup()

    # With the CM-based system, cleanup exceptions propagate to the caller
    with pytest.raises(RuntimeError, match="Cleanup failed"):
        await use_resource()

    _ = cleanup_tracker


@pytest.mark.skip_wire
async def test_generator_cleanup_with_stop_iteration(mocker: MockerFixture) -> None:
    """Test that a CM that yields once and exits cleanly works correctly."""
    from contextlib import asynccontextmanager

    @register_provider(context_manager=True)
    @asynccontextmanager
    async def normal_provider() -> AsyncGenerator[MagicMock, None]:
        resource = mocker.MagicMock()
        resource.value = "test"
        yield resource
        # Provider naturally ends here

    @inject
    async def use_resource(resource: Any = Depends[normal_provider]) -> str:
        return resource.value

    setup()

    result = await use_resource()
    assert result == "test"


@pytest.mark.skip_wire
async def test_async_generator_with_async_dependency_coroutine_resolution() -> None:
    """Test async CM provider resolving an async dependency."""
    from contextlib import asynccontextmanager

    @register_provider()
    async def async_dep() -> int:
        return 777

    @register_provider(context_manager=True)
    @asynccontextmanager
    async def gen_with_async_dep(
        val: int = Depends[async_dep],
    ) -> AsyncGenerator[int, None]:
        try:
            yield val * 2
        finally:
            pass

    @inject
    async def consumer(value: int = Depends[gen_with_async_dep]) -> int:
        return value

    result = await consumer()
    assert result == 1554  # 777 * 2

    clear_overrides()


@pytest.mark.skip_wire
async def test_async_function_with_async_dependency_coroutine_resolution() -> None:
    """Test async function resolving an async dependency that's a coroutine."""

    @register_provider()
    async def async_dep() -> int:
        return 555

    @register_provider()
    async def func_with_async_dep(val: int = Depends[async_dep]) -> int:
        return val * 3

    @inject
    async def consumer(value: int = Depends[func_with_async_dep]) -> int:
        return value

    result = await consumer()
    assert result == 1665  # 555 * 3

    clear_overrides()


@pytest.mark.skip_wire
def test_singleton_sync_cm_entered_once_and_teardown_on_shutdown() -> None:
    """A singleton sync CM provider is entered once and its teardown runs on
    registry shutdown, even when the injected function is called multiple times.

    singleton=True + context_manager=True registers the provider as a
    providers.Resource, which caches the yielded value after the first
    __enter__. Subsequent calls return the same object without re-entering.
    Teardown runs once when registry.shutdown_resources() is called.
    """
    enter_count = 0
    exit_count = 0

    @register_provider(singleton=True, context_manager=True)
    @contextmanager
    def shared_resource() -> Generator[dict[str, int], None, None]:
        nonlocal enter_count, exit_count
        enter_count += 1
        resource = {"id": enter_count}
        try:
            yield resource
        finally:
            exit_count += 1

    @inject
    def use_resource(res: dict[str, int] = Depends[shared_resource]) -> dict[str, int]:
        return res

    setup()

    result1 = use_resource()
    result2 = use_resource()

    assert enter_count == 1, "CM should be entered only once for a singleton"
    assert exit_count == 0, "Teardown should not run until shutdown"
    assert result1 is result2, "Both calls should return the same cached object"

    registry.shutdown_resources()

    assert exit_count == 1, "Teardown should run exactly once on shutdown"


@pytest.mark.skip_wire
async def test_singleton_async_cm_entered_once_and_teardown_on_shutdown() -> None:
    """A singleton async CM provider is entered once and its teardown runs on
    registry shutdown, even when the injected function is called multiple times.

    singleton=True + context_manager=True registers the provider as a
    providers.Resource, which caches the yielded value after the first
    __aenter__. Subsequent calls return the same object without re-entering.
    Teardown runs once when registry.shutdown_resources() is awaited.
    """
    enter_count = 0
    exit_count = 0

    @register_provider(singleton=True, context_manager=True)
    @asynccontextmanager
    async def shared_resource() -> AsyncGenerator[dict[str, int], None]:
        nonlocal enter_count, exit_count
        enter_count += 1
        resource = {"id": enter_count}
        try:
            yield resource
        finally:
            exit_count += 1

    @inject
    async def use_resource(
        res: dict[str, int] = Depends[shared_resource],
    ) -> dict[str, int]:
        return res

    setup()

    result1 = await use_resource()
    result2 = await use_resource()

    assert enter_count == 1, "CM should be entered only once for a singleton"
    assert exit_count == 0, "Teardown should not run until shutdown"
    assert result1 is result2, "Both calls should return the same cached object"

    await registry.shutdown_resources()  # pyright: ignore[reportGeneralTypeIssues]

    assert exit_count == 1, "Teardown should run exactly once on shutdown"
