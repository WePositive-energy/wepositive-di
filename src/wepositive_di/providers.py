from collections.abc import Coroutine
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Any, TypeVar

from dependency_injector import providers

_T = TypeVar("_T")


class CMFactory(providers.Factory[AbstractContextManager[_T]]):
    """Provider that creates a new sync context manager on every call.

    The inject decorator detects this type and automatically calls `__enter__`,
    passes the yielded value to the dependant function, then calls `__exit__`
    with any exception raised — transparently to the caller.
    """


class AsyncCMFactory(
    providers.Factory[Coroutine[Any, Any, AbstractAsyncContextManager[_T]]]
):
    """Provider that creates a new async context manager on every call.

    The wrapper function is async (to resolve async Depends), so calling this
    provider returns a coroutine that resolves to the context manager object.
    The inject decorator awaits it to get the CM, then calls `__aenter__`, passes
    the yielded value to the dependant function, and calls `__aexit__` with any
    exception raised — transparently to the caller.
    """


class SyncSingletonCMFactory(providers.Resource[_T]):
    """Singleton sync context manager provider.

    Inherits from providers.Resource so that the underlying context manager is
    entered once, the yielded value is cached, and teardown is triggered by
    registry.shutdown_resources(). Calling this provider returns the cached
    value directly (no await needed).
    """


class AsyncSingletonCMFactory(providers.Resource[_T]):
    """Singleton async context manager provider.

    Inherits from providers.Resource so that the underlying context manager is
    entered once, the yielded value is cached, and teardown is triggered by
    registry.shutdown_resources(). Calling this provider returns a coroutine on
    the first call (before the value is cached); the inject decorator awaits it
    to obtain the yielded value.
    """
