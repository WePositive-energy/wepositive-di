import asyncio
import functools
import inspect
import logging
import sys
import typing
from collections.abc import Callable, Coroutine
from contextlib import (
    AbstractAsyncContextManager,
    AbstractContextManager,
    contextmanager,
)
from typing import (
    Any,
    TypeVar,
    overload,
)

from dependency_injector import containers, providers

from wepositive_di.providers import (
    AsyncCMFactory as _AsyncCMFactory,
)
from wepositive_di.providers import (
    AsyncSingletonCMFactory as _AsyncSingletonCMFactory,
)
from wepositive_di.providers import (
    CMFactory as _CMFactory,
)
from wepositive_di.providers import (
    SyncSingletonCMFactory as _SyncSingletonCMFactory,
)

logger = logging.getLogger(__name__)

_registered_modules: set[Any] = set()
_provider_overrides: dict[str, providers.Provider[Any]] = {}
_context_manager_providers: set[str] = set()

registry = containers.DynamicContainer()


def _detect_lifecycle(
    func: Callable[..., Any],
    enter_attr: str,
    exit_attr: str,
    cache_attr: str,
    generator_predicate: Callable[[Any], bool],
) -> bool:
    cached = getattr(func, cache_attr, None)
    if cached is not None:
        return cached  # type: ignore[return-value]

    result = generator_predicate(getattr(func, "__wrapped__", None))
    try:
        hints = typing.get_type_hints(func)
        return_type = hints.get("return")
        if return_type is not None:
            result = result or (
                hasattr(return_type, enter_attr) and hasattr(return_type, exit_attr)
            )
    except Exception:  # noqa: BLE001
        pass

    try:
        setattr(func, cache_attr, result)
    except (AttributeError, TypeError):
        pass
    return result


def _is_async_lifecycle_annotation(func: Callable[..., Any]) -> bool:
    """Return True if *func* produces an async context manager.

    Detects two patterns:
    1. Functions decorated with @asynccontextmanager — identified via the code
       object's co_qualname, which @wraps cannot change.
    2. Functions whose return type annotation has `__aenter__`/`__aexit__` (either
       directly on the class, or proxied through a generic alias to its origin).
    """
    return _detect_lifecycle(
        func,
        "__aenter__",
        "__aexit__",
        "_di_is_async_lifecycle",
        inspect.isasyncgenfunction,
    )


def _is_sync_lifecycle_annotation(func: Callable[..., Any]) -> bool:
    """Return True if *func* produces a sync context manager.

    Detects two patterns:
    1. Functions decorated with @contextmanager — identified via the code
       object's co_qualname, which @wraps cannot change.
    2. Functions whose return type annotation has `__enter__`/`__exit__` (either
       directly on the class, or proxied through a generic alias to its origin).
    """
    return _detect_lifecycle(
        func,
        "__enter__",
        "__exit__",
        "_di_is_sync_lifecycle",
        inspect.isgeneratorfunction,
    )


def _lookup_provider(name: str) -> Any:
    """Return the provider callable for *name*, checking overrides first."""
    if name in _provider_overrides:
        return _provider_overrides[name]
    return getattr(registry, name)


def _uses_context_manager(provider_name: str) -> bool:
    return provider_name in _context_manager_providers


def _resolve_deps_sync(
    sig: inspect.Signature, provider_name: str, func_name: str
) -> dict[str, Any]:
    """Resolve Depends[...] markers in *sig* synchronously.

    Raises RuntimeError if any dependency resolves to a coroutine — sync
    providers cannot have async dependencies.
    """
    bound = sig.bind_partial()
    bound.apply_defaults()
    for param_name in list(bound.arguments.keys()):
        value = bound.arguments[param_name]
        if isinstance(value, _DependsMarker):
            result = _lookup_provider(value.name)()
            if asyncio.iscoroutine(result):
                result.close()
                raise RuntimeError(
                    f"Cannot resolve async dependency '{param_name}' in sync provider "
                    f"'{provider_name}'. Sync providers cannot have async dependencies. "
                    f"Make your provider async instead: async def {func_name}(...)"
                )
            bound.arguments[param_name] = result
    return bound.arguments


async def _resolve_deps_async(sig: inspect.Signature) -> dict[str, Any]:
    """Resolve Depends[...] markers in *sig*, awaiting any async results."""
    bound = sig.bind_partial()
    bound.apply_defaults()
    for param_name in list(bound.arguments.keys()):
        value = bound.arguments[param_name]
        if isinstance(value, _DependsMarker):
            result = _lookup_provider(value.name)()
            if asyncio.iscoroutine(result):
                result = await result
            bound.arguments[param_name] = result
    return bound.arguments


def _create_provider(
    func: Callable[..., Any],
    *,
    provider_name: str | None = None,
    singleton: bool = False,
    context_manager: bool = False,
) -> providers.Provider[Any]:
    """Wrap *func* as the appropriate provider type, with Depends resolution.

    Provider type is chosen based on the function's characteristics:
    - Async context manager + singleton → providers.Resource
    - Async context manager             → AsyncCMFactory
    - Sync context manager + singleton  → providers.Resource
    - Sync context manager              → CMFactory
    - Plain async function              → providers.Coroutine
    - Sync singleton                    → providers.Singleton
    - Sync factory (default)            → providers.Factory
    """
    name = provider_name or func.__name__
    sig = inspect.signature(func)
    is_async_cm = context_manager and _is_async_lifecycle_annotation(func)
    is_sync_cm = context_manager and _is_sync_lifecycle_annotation(func)
    is_async_func = inspect.iscoroutinefunction(func)

    if context_manager and not (is_async_cm or is_sync_cm):
        raise ValueError(
            f"Provider '{name}' was registered with context_manager=True, "
            "but it does not return a supported sync or async context manager."
        )

    if is_async_cm:

        async def async_cm_wrapper():
            return func(**(await _resolve_deps_async(sig)))

        if singleton:
            return _AsyncSingletonCMFactory(async_cm_wrapper)
        return _AsyncCMFactory(async_cm_wrapper)

    elif is_sync_cm:

        def sync_cm_wrapper():
            return func(**_resolve_deps_sync(sig, name, func.__name__))

        if singleton:
            return _SyncSingletonCMFactory(sync_cm_wrapper)
        return _CMFactory(sync_cm_wrapper)  # type: ignore[return-value]

    elif is_async_func:

        async def async_func_wrapper():
            return await func(**(await _resolve_deps_async(sig)))

        return providers.Coroutine(async_func_wrapper)

    else:

        def sync_wrapper():
            return func(**_resolve_deps_sync(sig, name, func.__name__))

        if singleton:
            return providers.Singleton(sync_wrapper)
        return providers.Factory(sync_wrapper)  # type: ignore[return-value]


def register_provider(
    name: str | None = None,
    singleton: bool = False,
    context_manager: bool = False,
):
    def decorator(func: Callable[..., Any]):
        """Register a provider function (sync or async) in the registry.

        Args:
            name: Optional name for the provider (defaults to function name)
            singleton: If True, caches and reuses the first created instance.
            context_manager: If True, enter and exit the provider's context manager
                when resolving dependencies. Context-manager handling is opt-in.
        """
        provider_name = name or func.__name__
        is_async_func = inspect.iscoroutinefunction(func)

        if is_async_func and not context_manager and singleton:
            raise ValueError(
                f"Async provider '{provider_name}' cannot be a singleton. "
                f"The dependency-injector library doesn't support singleton caching for Coroutine providers. "
                f"Make your provider a sync function instead: def {func.__name__}(...)"
            )

        provider = _create_provider(
            func,
            provider_name=provider_name,
            singleton=singleton,
            context_manager=context_manager,
        )
        setattr(registry, provider_name, provider)
        if context_manager:
            _context_manager_providers.add(provider_name)
        else:
            _context_manager_providers.discard(provider_name)

        module = inspect.getmodule(func)
        if module is not None:  # pragma: no branch
            _registered_modules.add(module)
        return func

    return decorator


def setup(
    overrides: dict[Callable[..., Any] | str, Callable[..., Any]] | None = None,
):
    """Wire the dependency injection system.

    Args:
        overrides: Optional dictionary of provider overrides to apply before wiring.
                  Maps original providers to their override implementations.

    Usage:

    ```python
    setup()

    def redis_storage() -> ContextStorage:
        return RedisContextStorage()

    setup(overrides={context_storage_singleton: redis_storage})
    ```
    """
    if overrides:
        for original, override_func in overrides.items():
            provider_name = original if isinstance(original, str) else original.__name__
            _provider_overrides[provider_name] = _create_provider(
                override_func,
                provider_name=provider_name,
                context_manager=_uses_context_manager(provider_name),
            )

    registry.wire(modules=list(_registered_modules))


@overload
def override_provider(
    original: Callable[..., Any] | str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


@overload
def override_provider(
    original: Callable[..., Any] | str,
    override: Callable[..., Any],
) -> None: ...


def override_provider(
    original: Callable[..., Any] | str,
    override: Callable[..., Any] | None = None,
) -> None | Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Override a provider with a new implementation.

    Can be used as a function or a decorator.

    Args:
        original: The original provider function or its name
        override: The new provider function (when used as a function call)

    Returns:
        None when used as a function, decorator when used as @override_provider(original)

    Usage:

    ```python
    @register_provider()
    async def config() -> Config:
        return Config()

    async def prod_config() -> Config:
        return Config(db_url="production")

    override_provider(config, prod_config)
    ```

    ```python
    @override_provider(config)
    async def prod_config() -> Config:
        return Config(db_url="production")
    ```
    """
    provider_name = original if isinstance(original, str) else original.__name__

    # Used as @override_provider(original)
    if override is None:

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            _provider_overrides[provider_name] = _create_provider(
                func,
                provider_name=provider_name,
                context_manager=_uses_context_manager(provider_name),
            )
            return func

        return decorator

    # Used as override_provider(original, override_func)
    _provider_overrides[provider_name] = _create_provider(
        override,
        provider_name=provider_name,
        context_manager=_uses_context_manager(provider_name),
    )
    return None


def clear_overrides() -> None:
    """Clear all provider overrides."""
    _provider_overrides.clear()


@contextmanager
def provider_overrides(
    overrides: dict[Callable[..., Any] | str, Callable[..., Any]],
):
    """Context manager to temporarily override providers for testing.

    Args:
        overrides: Dictionary mapping original providers to their overrides

    Usage:

    ```python
    async def test_config() -> Config:
        return Config(sqlalchemy_db_uri=SecretStr("sqlite:///:memory:"))

    with provider_overrides({config: test_config}):
        result = await my_function()
    ```
    """
    # Save current state
    old_overrides = _provider_overrides.copy()

    # Apply new overrides
    for original, override in overrides.items():
        provider_name = original if isinstance(original, str) else original.__name__
        _provider_overrides[provider_name] = _create_provider(
            override,
            provider_name=provider_name,
            context_manager=_uses_context_manager(provider_name),
        )

    try:
        yield
    finally:
        # Restore previous state
        _provider_overrides.clear()
        _provider_overrides.update(old_overrides)


class _DependsMarker:
    """Marker class for lazy dependency injection."""

    def __init__(self, name: str):
        self.name = name


class _DependsType:
    """Subscriptable type for Depends[func] syntax."""

    def __getitem__(self, func: Callable[..., Any] | str) -> Any:
        """Create a dependency marker using subscript notation.

        Usage: def my_func(config: Config = Depends[config]):
        """
        if isinstance(func, str):
            name = func
        else:
            name = func.__name__

        return _DependsMarker(name)


Depends = _DependsType()

T = TypeVar("T", bound=Callable[..., Any])


@contextmanager
def _create_event_loop(param_name: str, func_name: str):
    has_running_loop = False
    try:
        asyncio.get_running_loop()
        has_running_loop = True
    except RuntimeError:
        # No running loop - this is fine
        pass

    if has_running_loop:
        # Can't use run_until_complete in an already-running loop
        raise RuntimeError(
            f"Cannot resolve async dependency '{param_name}' in sync function "
            f"'{func_name}' from within an async context. "
            f"Either make '{func_name}' async or call it from a sync context."
        )

    # No running loop - create one for this sync context
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@overload
def inject(
    func: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Coroutine[Any, Any, Any]]: ...


@overload
def inject(func: Callable[..., Any]) -> Callable[..., Any]: ...


def inject(func: T) -> T:
    """Decorator that resolves Depends markers in function arguments.

    Works with both sync and async functions.

    The decorator:

    - Inspects the function signature for `_DependsMarker` defaults.
    - At call time, resolves each marker by calling the registry provider.
    - Handles context manager providers transparently: enters the context manager,
      passes the yielded value to the function, and exits on completion.
    - Returns the appropriate wrapper based on the function type.

    Provider types and how they are resolved:

    - AsyncCMFactory: await coroutine, get context manager, await `__aenter__`.
    - CMFactory: get context manager, call `__enter__`.
    - providers.Coroutine: await result.
    - providers.Factory / providers.Singleton: use result directly.

    Usage:

    ```python
    @inject
    def my_func(config: Config = Depends[config]):
        return config.value

    @inject
    async def my_async_func(session: AsyncSession = Depends[async_session]):
        return session.query(...)
    ```

    """
    sig = inspect.signature(func)
    dependant_is_async = inspect.iscoroutinefunction(
        func
    ) or inspect.isasyncgenfunction(func)

    async def _resolve_dependencies_async(
        args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[
        dict[str, Any],
        set[AbstractAsyncContextManager[Any]],
        set[AbstractContextManager[Any]],
    ]:
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        sync_lifecycles_to_cleanup: set[AbstractContextManager[Any]] = set()
        async_lifecycles_to_cleanup: set[AbstractAsyncContextManager[Any]] = set()

        for param_name in list(bound.arguments.keys()):
            value = bound.arguments[param_name]
            if not isinstance(value, _DependsMarker):
                continue
            provider = _lookup_provider(value.name)
            result = provider()

            if isinstance(provider, _AsyncSingletonCMFactory):
                result = await result
            elif isinstance(provider, _SyncSingletonCMFactory):
                pass  # sync Resource returns the cached value directly
            elif isinstance(provider, _AsyncCMFactory):
                cm = await result  # await async wrapper to get the CM object
                async_lifecycles_to_cleanup.add(cm)
                result = await cm.__aenter__()
            elif isinstance(provider, _CMFactory):
                cm = result  # sync wrapper returns the CM directly
                sync_lifecycles_to_cleanup.add(cm)
                result = cm.__enter__()
            elif isinstance(provider, providers.Coroutine):
                result = await result

            bound.arguments[param_name] = result

        return bound.arguments, async_lifecycles_to_cleanup, sync_lifecycles_to_cleanup

    def _resolve_dependencies_sync(
        args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[
        dict[str, Any],
        set[AbstractAsyncContextManager[Any]],
        set[AbstractContextManager[Any]],
    ]:
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        sync_lifecycles_to_cleanup: set[AbstractContextManager[Any]] = set()
        async_lifecycles_to_cleanup: set[AbstractAsyncContextManager[Any]] = set()

        for param_name in list(bound.arguments.keys()):
            value = bound.arguments[param_name]
            if not isinstance(value, _DependsMarker):
                continue
            provider = _lookup_provider(value.name)
            result = provider()

            if isinstance(provider, _AsyncSingletonCMFactory):
                with _create_event_loop(param_name, func.__name__) as loop:
                    result = loop.run_until_complete(result)
            elif isinstance(provider, _SyncSingletonCMFactory):
                pass  # sync Resource returns the cached value directly
            elif isinstance(provider, _AsyncCMFactory):
                with _create_event_loop(param_name, func.__name__) as loop:
                    cm = loop.run_until_complete(result)  # await async wrapper → CM
                    async_lifecycles_to_cleanup.add(cm)
                    result = loop.run_until_complete(cm.__aenter__())
            elif isinstance(provider, _CMFactory):
                cm = result
                sync_lifecycles_to_cleanup.add(cm)
                result = cm.__enter__()
            elif isinstance(provider, providers.Coroutine):
                with _create_event_loop(param_name, func.__name__) as loop:
                    result = loop.run_until_complete(result)

            bound.arguments[param_name] = result

        return bound.arguments, async_lifecycles_to_cleanup, sync_lifecycles_to_cleanup

    if dependant_is_async:

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            (
                resolved_args,
                async_lifecycles_to_cleanup,
                sync_lifecycles_to_cleanup,
            ) = await _resolve_dependencies_async(args, kwargs)

            exc_info = (None, None, None)
            try:
                result = await func(**resolved_args)
                return result
            except Exception:
                exc_info = sys.exc_info()
                raise
            finally:
                suppressed = False
                for cm in async_lifecycles_to_cleanup:
                    if await cm.__aexit__(*exc_info):
                        suppressed = True
                for cm in sync_lifecycles_to_cleanup:
                    if cm.__exit__(*exc_info):
                        suppressed = True
                if exc_info[0] is not None and not suppressed:
                    raise exc_info[1].with_traceback(exc_info[2])  # type: ignore[union-attr]

        return async_wrapper  # type: ignore
    else:

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            resolved_args, async_lifecycles_to_cleanup, sync_lifecycles_to_cleanup = (
                _resolve_dependencies_sync(args, kwargs)
            )
            exc_info = (None, None, None)
            try:
                result = func(**resolved_args)
                return result
            except Exception:
                exc_info = sys.exc_info()
                raise
            finally:
                suppressed = False
                for cm in async_lifecycles_to_cleanup:
                    cm_name = getattr(cm, "__wrapped__", type(cm)).__name__
                    with _create_event_loop(cm_name, func.__name__) as loop:
                        if loop.run_until_complete(cm.__aexit__(*exc_info)):
                            suppressed = True
                for cm in sync_lifecycles_to_cleanup:
                    if cm.__exit__(*exc_info):
                        suppressed = True
                if exc_info[0] is not None and not suppressed:
                    raise exc_info[1].with_traceback(exc_info[2])  # type: ignore[union-attr]

        return sync_wrapper  # type: ignore
