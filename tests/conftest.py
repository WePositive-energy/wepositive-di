import inspect
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest

from wepositive_di import di
from wepositive_di.context import context_storage_singleton


def _reset_di_registry() -> None:
    shutdown_result = di.registry.shutdown_resources()
    if inspect.iscoroutine(shutdown_result):
        shutdown_result.close()

    for provider_name in list(di.registry.providers):
        if provider_name == "__self__":
            continue
        delattr(di.registry, provider_name)

    di.clear_overrides()
    registered_modules = cast(set[Any], getattr(di, "_registered_modules"))
    registered_modules.clear()
    context_manager_providers = cast(
        set[str], getattr(di, "_context_manager_providers")
    )
    context_manager_providers.clear()


@pytest.fixture(autouse=True)
def isolated_di_registry() -> Iterator[None]:
    _reset_di_registry()
    try:
        yield
    finally:
        _reset_di_registry()


@pytest.fixture
def wire_providers() -> Callable[..., None]:
    def factory(
        overrides: dict[Callable[..., Any] | str, Callable[..., Any]] | None = None,
    ) -> None:
        di.setup(overrides=overrides)

    return factory


@pytest.fixture
def context_storage_provider() -> Callable[[], Any]:
    di.register_provider(singleton=True)(context_storage_singleton)
    return context_storage_singleton
