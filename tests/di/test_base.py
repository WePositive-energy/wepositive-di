import concurrent.futures
from typing import Any

import pytest

from wepositive_di import (
    Depends as RootDepends,
)
from wepositive_di import (
    clear_overrides as root_clear_overrides,
)
from wepositive_di import (
    context as root_context,
)
from wepositive_di import (
    inject as root_inject,
)
from wepositive_di import (
    override_provider as root_override_provider,
)
from wepositive_di import (
    provider_overrides as root_provider_overrides,
)
from wepositive_di import (
    register_provider as root_register_provider,
)
from wepositive_di import (
    registry as root_registry,
)
from wepositive_di import (
    setup as root_setup,
)
from wepositive_di.di import (
    Depends,
    clear_overrides,
    inject,
    register_provider,
    setup,
)


async def test_dependency_injection():
    @register_provider()
    async def config() -> dict[str, str]:
        return {"value": "test_value"}

    @inject
    def my_test_function(config: dict[str, str] = Depends[config]):
        return config["value"]

    @inject
    async def my_test_function2(config: dict[str, str] = Depends[config]):
        return config["value"]

    setup()

    with pytest.raises(
        RuntimeError,
        match=r"Cannot resolve async dependency 'config' in sync function 'my_test_function' from within an async context\. Either make 'my_test_function' async or call it from a sync context\.",
    ):
        assert my_test_function() == "test_value"

    assert await my_test_function2() == "test_value"


def test_common_di_api_is_available_from_package_root() -> None:
    assert RootDepends is Depends
    assert root_clear_overrides is clear_overrides
    assert root_inject is inject
    assert root_register_provider is register_provider
    assert root_setup is setup
    assert root_registry is not None
    assert root_context is not None
    assert callable(root_override_provider)
    assert callable(root_provider_overrides)


def test_singleton_works_for_sync():
    """Test that sync functions with singleton=True cache the result."""
    call_count = 0

    @register_provider(singleton=True)
    def counter() -> int:
        nonlocal call_count
        call_count += 1
        return call_count

    @inject
    def get_counter(c: int = Depends[counter]) -> int:
        return c

    setup()

    # First call - creates instance
    result1 = get_counter()
    assert result1 == 1

    # Second call - returns cached instance
    result2 = get_counter()
    assert result2 == 1  # Still 1, proving it's cached!

    # Provider was only called once
    assert call_count == 1


def test_singleton_raises_error_for_async():
    """Test that async functions cannot use singleton=True."""
    with pytest.raises(ValueError, match="cannot be a singleton"):  # noqa: PT012

        @register_provider(singleton=True)
        async def async_counter() -> int:
            return 42

        async_counter()


def test_depends_with_string_name() -> None:
    """Test that Depends["string_name"] syntax works correctly."""

    @register_provider()
    def my_config() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        return {"value": 42}

    @inject
    def consumer(cfg: dict[str, Any] = Depends["my_config"]) -> int:
        return cfg["value"]

    result = consumer()
    assert result == 42

    clear_overrides()


def test_inject_asyncio_run_path() -> None:
    """Test inject decorator using asyncio.run when no event loop."""

    @register_provider()
    async def async_dep() -> int:
        return 555

    @inject
    async def async_consumer(value: int = Depends[async_dep]) -> int:
        return value

    def call_in_thread() -> int:
        import asyncio

        return asyncio.run(async_consumer())

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(call_in_thread)
        result = future.result()

    assert result == 555

    clear_overrides()


def test_setup_with_overrides_dict() -> None:
    """setup(overrides={...}) applies overrides before wiring.

    Covers lines 273-275: the for-loop inside setup() that populates
    _provider_overrides from the dict argument.
    """

    @register_provider()
    def original() -> str:
        return "original"

    def replacement() -> str:
        return "replaced"

    @inject
    def consumer(val: str = Depends[original]) -> str:
        return val

    setup(overrides={original: replacement})
    try:
        assert consumer() == "replaced"
    finally:
        clear_overrides()
