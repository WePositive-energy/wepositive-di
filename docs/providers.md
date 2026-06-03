# Providers

Providers are normal Python callables decorated with
[`@register_provider()`](api/di.md#wepositive_di.di.register_provider). A
provider may depend on other providers by using `Depends[...]` in its own
signature.

## Provider matrix

| Provider shape | Options | Lifetime | Cleanup | Notes |
| --- | --- | --- | --- | --- |
| Sync function | `@register_provider()` | New value per resolution | None | Can depend only on sync providers. |
| Sync singleton | `@register_provider(singleton=True)` | One cached value per process | None | Good for clients, config, caches. |
| Async function | `@register_provider()` | New awaited value per resolution | None | Can depend on sync or async providers. |
| Sync context manager | `@register_provider(context_manager=True)` | Entered per injected call | On call exit | Uses `@contextmanager` or a sync context manager return type. |
| Async context manager | `@register_provider(context_manager=True)` | Entered per injected call | On call exit | Uses `@asynccontextmanager` or an async context manager return type. |
| Sync singleton context manager | `@register_provider(singleton=True, context_manager=True)` | Entered once, cached | `registry.shutdown_resources()` | Backed by `dependency_injector.providers.Resource`. |
| Async singleton context manager | `@register_provider(singleton=True, context_manager=True)` | Entered once, cached | `await registry.shutdown_resources()` | Useful for async clients with explicit shutdown. |

Plain async providers cannot use `singleton=True`; use a sync provider or a
singleton context manager provider instead.

## Sync factory provider

```python
from wepositive_di import register_provider


@register_provider()
def request_id() -> str:
    return "request-123"
```

The provider is called every time it is resolved.

## Sync singleton provider

```python
from wepositive_di import register_provider


class MetricsClient:
    pass


@register_provider(singleton=True)
def metrics_client() -> MetricsClient:
    return MetricsClient()
```

The first result is cached for the process lifetime.

## Async provider

```python
from wepositive_di import Depends, register_provider


@register_provider()
def api_base_url() -> str:
    return "https://api.example.com"


@register_provider()
async def api_client(base_url: str = Depends[api_base_url]) -> str:
    return f"client:{base_url}"
```

Async providers can depend on sync or async providers.

## Context manager providers

Context manager providers are for resources that must be entered and exited
around the injected function call.

```python
from collections.abc import Generator
from contextlib import contextmanager

from wepositive_di import register_provider


@register_provider(context_manager=True)
@contextmanager
def file_handle() -> Generator[object, None, None]:
    handle = open("/tmp/example.txt")
    try:
        yield handle
    finally:
        handle.close()
```

Always use `try`/`finally` or equivalent cleanup logic. Exceptions raised by the
injected function are passed into the context manager's exit method.

## Singleton context manager providers

Singleton context manager providers are entered once and remain active until the
dependency-injector registry resources are shut down.

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from wepositive_di import register_provider, registry


@register_provider(singleton=True, context_manager=True)
@asynccontextmanager
async def shared_client() -> AsyncGenerator[dict[str, bool], None]:
    client = {"connected": True}
    try:
        yield client
    finally:
        client["connected"] = False


# Later, during application shutdown:
await registry.shutdown_resources()
```

Use `registry.shutdown_resources()` for sync resources and
`await registry.shutdown_resources()` for async resources.

## Injection rules

| Call site | Dependency type | Supported |
| --- | --- | --- |
| Async function | Sync provider | Yes |
| Async function | Async provider | Yes |
| Sync function without running event loop | Sync provider | Yes |
| Sync function without running event loop | Async provider | Yes, a temporary event loop is created |
| Sync function inside a running event loop | Async provider | No |
| Sync provider | Async dependency | No |

If a sync function needs an async dependency in an async application, make the
function async.

## Named providers

Use a custom provider name when a dependency should be referenced by string.

```python
from wepositive_di import Depends, inject, register_provider


@register_provider(name="config")
def production_config() -> dict[str, str]:
    return {"env": "production"}


@inject
def read_env(cfg: dict[str, str] = Depends["config"]) -> str:
    return cfg["env"]
```
