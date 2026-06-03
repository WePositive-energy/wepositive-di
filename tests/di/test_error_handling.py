"""Tests for error handling scenarios in dependency injection."""

import concurrent.futures
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
    setup,
)


@pytest.fixture
def mock_config(mocker: MockerFixture) -> MagicMock:
    """Mock config object."""
    config = mocker.MagicMock()
    config.value = "test_config"
    config.api_url = "https://api.example.com"
    return config


@pytest.mark.skip_wire
async def test_sync_provider_with_async_dependency_in_event_loop(
    mocker: MockerFixture, mock_config: MagicMock
) -> None:
    """Test error when sync provider tries to resolve async dependency with event loop running.

    This tests lines 108-114: RuntimeError when asyncio.get_running_loop() succeeds.
    """

    @register_provider()
    async def async_config() -> Any:
        return mock_config

    @register_provider()
    def sync_provider_needs_async(cfg: Any = Depends[async_config]) -> Any:
        # This sync provider depends on an async provider
        return cfg.value

    @inject
    async def use_sync_provider(value: Any = Depends[sync_provider_needs_async]) -> Any:
        return value

    setup()

    # Execute from async context (event loop is running)
    # This should raise an error because sync provider can't resolve async dependency
    # when called from an event loop context
    with pytest.raises(
        RuntimeError,
        match=r"Cannot resolve async dependency 'cfg' in sync provider 'sync_provider_needs_async'\. Sync providers cannot have async dependencies\. Make your provider async instead: async def sync_provider_needs_async\(\.\.\.\)",
    ):
        await use_sync_provider()


@pytest.mark.skip_wire
def test_sync_provider_with_async_dependency_no_event_loop(
    mocker: MockerFixture, mock_config: MagicMock
) -> None:
    """Test sync provider with async dependency raises error (no asyncio.run fallback).

    With the new behavior, sync providers cannot resolve async dependencies
    regardless of whether there's an event loop or not.
    """

    @register_provider()
    async def async_config() -> Any:
        return mock_config

    @register_provider()
    def sync_provider_needs_async(cfg: Any = Depends[async_config]) -> Any:
        # This sync provider depends on an async provider
        return cfg.value

    @inject
    def use_sync_provider(value: Any = Depends[sync_provider_needs_async]) -> Any:
        return value

    setup()

    # Should raise an error because sync provider can't resolve async dependency
    with pytest.raises(
        RuntimeError,
        match=r"Cannot resolve async dependency 'cfg' in sync provider 'sync_provider_needs_async'\. Sync providers cannot have async dependencies\. Make your provider async instead: async def sync_provider_needs_async\(\.\.\.\)",
    ):
        use_sync_provider()  # pyright: ignore[reportUnusedCoroutine]


@pytest.mark.skip_wire
async def test_sync_dependency_error_handling_in_event_loop(
    mocker: MockerFixture,
) -> None:
    """Test error handling when sync function resolves async dependency in event loop.

    Sync functions cannot resolve async dependencies when called from an async
    context (event loop already running). The DI system raises a clear error.
    """

    @register_provider()
    async def async_dep() -> str:
        return "async_value"

    @inject
    def sync_func_with_async_dep(val: Any = Depends[async_dep]) -> Any:
        return val

    # Call from async context to trigger the error
    async def caller() -> Any:
        return sync_func_with_async_dep()

    with pytest.raises(
        RuntimeError,
        match=r"Cannot resolve async dependency 'val' in sync function 'sync_func_with_async_dep' from within an async context\. Either make 'sync_func_with_async_dep' async or call it from a sync context\.",
    ):
        await caller()


@pytest.mark.skip_wire
async def test_exception_propagation_through_dependency_chain(
    mocker: MockerFixture,
) -> None:
    """Test that exceptions propagate correctly through dependency chains."""

    @register_provider()
    async def failing_provider() -> Any:
        raise ValueError("Provider failed")

    @inject
    async def function_with_failing_dep(val: Any = Depends[failing_provider]) -> Any:
        return val

    setup()

    # Exception from provider should propagate
    with pytest.raises(ValueError, match="Provider failed"):
        await function_with_failing_dep()


@pytest.mark.skip_wire
async def test_async_generator_with_exception_in_athrow(mocker: MockerFixture) -> None:
    """Test async CM cleanup when function raises exception."""
    cleanup_called = False

    @register_provider(context_manager=True)
    @asynccontextmanager
    async def generator_with_exception_handler() -> AsyncGenerator[Any, None]:
        resource: Any = mocker.MagicMock()
        try:
            yield resource
        finally:
            nonlocal cleanup_called
            cleanup_called = True

    @inject
    async def failing_function(
        resource: Any = Depends[generator_with_exception_handler],
    ) -> None:
        raise ValueError("Function error")

    setup()

    # Execute and verify exception is propagated from function
    with pytest.raises(ValueError, match="Function error"):
        await failing_function()

    # Verify the generator's cleanup code ran via finally block
    assert cleanup_called


@pytest.mark.skip_wire
def test_sync_generator_with_exception_in_throw(mocker: MockerFixture) -> None:
    """Test sync CM cleanup when function raises exception."""
    cleanup_called = False

    @register_provider(context_manager=True)
    @contextmanager
    def generator_with_exception_handler() -> Generator[Any, None, None]:
        resource: Any = mocker.MagicMock()
        try:
            yield resource
        finally:
            nonlocal cleanup_called
            cleanup_called = True

    @inject
    def failing_function(
        resource: Any = Depends[generator_with_exception_handler],
    ) -> None:
        raise OSError("Function error")

    setup()

    # Execute and verify exception is propagated from function
    with pytest.raises(IOError, match="Function error"):
        failing_function()

    # Verify the generator's cleanup code ran via finally block
    assert cleanup_called


@pytest.mark.skip_wire
async def test_async_generator_raises_different_exception_during_cleanup(
    mocker: MockerFixture,
) -> None:
    """Test when async CM raises a different exception during cleanup.

    When the generator raises a different exception during cleanup than the one
    thrown in, the new exception propagates (replacing the original).
    """

    @register_provider(context_manager=True)
    @asynccontextmanager
    async def generator_that_fails_cleanup() -> AsyncGenerator[Any, None]:
        resource: Any = mocker.MagicMock()
        try:
            yield resource
        except ValueError:
            raise RuntimeError("Cleanup error")

    @inject
    async def failing_function(
        resource: Any = Depends[generator_that_fails_cleanup],
    ) -> None:
        raise ValueError("Function error")

    setup()

    # The cleanup raises RuntimeError which propagates (replaces the original ValueError)
    with pytest.raises(RuntimeError, match="Cleanup error"):
        await failing_function()


@pytest.mark.skip_wire
def test_sync_generator_raises_different_exception_during_cleanup(
    mocker: MockerFixture,
) -> None:
    """Test when sync CM raises a different exception during cleanup.

    When the generator raises a different exception during cleanup than the one
    thrown in, the new exception propagates (replacing the original).
    """

    @register_provider(context_manager=True)
    @contextmanager
    def generator_that_fails_cleanup() -> Generator[Any, None, None]:
        resource: Any = mocker.MagicMock()
        try:
            yield resource
        except OSError:
            raise RuntimeError("Cleanup error")

    @inject
    def failing_function(resource: Any = Depends[generator_that_fails_cleanup]) -> None:
        raise OSError("Function error")

    setup()

    # The cleanup raises RuntimeError which propagates (replaces the original OSError)
    with pytest.raises(RuntimeError, match="Cleanup error"):
        failing_function()


@pytest.mark.skip_wire
async def test_mixed_sync_async_generators_cleanup(mocker: MockerFixture) -> None:
    """Test cleanup of both sync and async CM providers in same function."""
    cleanup_order: list[str] = []

    @register_provider(context_manager=True)
    @asynccontextmanager
    async def async_gen() -> AsyncGenerator[Any, None]:
        try:
            yield "async"
        finally:
            cleanup_order.append("async")

    @register_provider(context_manager=True)
    @contextmanager
    def sync_gen() -> Generator[Any, None, None]:
        try:
            yield "sync"
        finally:
            cleanup_order.append("sync")

    @inject
    async def use_both(a: Any = Depends[async_gen], s: Any = Depends[sync_gen]) -> None:
        raise ValueError("Test error")

    setup()

    # Both should be cleaned up despite exception
    with pytest.raises(ValueError, match="Test error"):
        await use_both()

    # Verify both were cleaned up
    assert "async" in cleanup_order
    assert "sync" in cleanup_order


@pytest.mark.skip_wire
async def test_sync_function_with_async_dependency_outside_event_loop() -> None:
    """Test sync provider with async dependency raises error even outside an event loop.

    Sync providers cannot resolve async dependencies regardless of event loop state.
    The test runs in a thread to simulate a true sync (no-event-loop) context.
    """

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

        with pytest.raises(
            RuntimeError,
            match=r"Cannot resolve async dependency 'val' in sync provider 'sync_func_with_async_dep'\.",
        ):
            consumer()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_thread)
        future.result()

    clear_overrides()


@pytest.mark.skip_wire
async def test_sync_gen_async_dep_error_in_async_context() -> None:
    """Test sync generator with async dependency raises RuntimeError in async context."""

    @register_provider()
    async def async_base() -> int:
        return 10

    @register_provider()
    def sync_gen(val: int = Depends[async_base]) -> int:
        return val

    @inject
    async def consumer(value: int = Depends[sync_gen]) -> int:
        return value

    with pytest.raises(RuntimeError, match="Cannot resolve async dependency"):
        await consumer()

    clear_overrides()


@pytest.mark.skip_wire
def test_inject_sync_func_with_async_dep_no_event_loop() -> None:
    """Test @inject sync function resolves async dep by creating a new event loop.

    The DI system creates a new event loop when no loop is running.
    Runs in a thread to guarantee no running event loop.
    """

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
