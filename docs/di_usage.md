# Dependency Injection Usage Guide

This guide explains how to use the DI system in `cem.di`.  It
covers registering providers, injecting them into functions, managing resources
with generator providers, and overriding providers for testing.

---

## Core Concepts

| Concept | What it does |
|---|---|
| [`@register_provider()`](../api/di.md#cem.di.register_provider) | Registers a function as a named provider in the DI registry |
| [`Depends[provider]`](../api/di.md#cem.di.Depends) | Marks a parameter as a dependency to be resolved at call time |
| [`@inject`](../api/di.md#cem.di.inject) | Wraps a function so its `Depends` parameters are resolved automatically |
| [`setup()`](../api/di.md#cem.di.setup) | Wires the registry — call once at application startup |

---

## Quick Start

```python
from cem.di import register_provider, Depends, inject, setup

@register_provider()
async def config() -> dict:
    return {"db_url": "postgresql://localhost/mydb", "debug": False}

@inject
async def get_db_url(cfg: dict = Depends[config]) -> str:
    return cfg["db_url"]

# Wire up the DI system at application startup
setup()

# cfg is injected automatically — no argument needed
url = await get_db_url()
```

---

## Registering Providers

### Async provider

```python
@register_provider()
async def settings() -> dict:
    # Could read from env vars, a config file, a database, etc.
    return {"timeout": 30, "retries": 3}
```

### Sync provider

```python
@register_provider()
def request_id() -> str:
    import uuid
    return str(uuid.uuid4())
```

### Singleton provider (sync only)

A singleton provider is called once and the result is cached for the lifetime
of the process.  Singletons are only supported for sync providers.

> **Note:** Async singletons are not supported due to a limitation in the
> underlying [dependency-injector](https://python-dependency-injector.ets-labs.org/)
> library, which does not support singleton caching for `Coroutine` providers.
> If you need a singleton, make your provider a sync function.

```python
@register_provider(singleton=True)
def metrics_client() -> MetricsClient:
    return MetricsClient(host="metrics.internal")
```

```python
# Async providers cannot be singletons — this raises ValueError:
@register_provider(singleton=True)   # ❌ raises ValueError
async def bad_singleton() -> str:
    return "value"
```

### Named provider

By default the provider is stored under the function name.  You can give it an
explicit name:

```python
@register_provider(name="db_config")
async def production_config() -> dict:
    return {"url": "postgresql://prod-host/mydb"}
```

---

## Injecting Dependencies

### Into an async function

```python
@inject
async def handle_request(cfg: dict = Depends[settings]) -> str:
    return f"timeout={cfg['timeout']}"
```

### Into a sync function

```python
@inject
def get_timeout(cfg: dict = Depends[settings]) -> int:
    return cfg["timeout"]
```

### Chained / nested dependencies

Providers can themselves depend on other providers.

```python
@register_provider()
async def db_config() -> dict:
    return {"host": "localhost", "port": 5432}

@register_provider()
async def connection_pool(cfg: dict = Depends[db_config]) -> dict:
    # cfg is resolved from db_config automatically
    return {"host": cfg["host"], "port": cfg["port"], "pool_size": 5}

@inject
async def run_query(pool: dict = Depends[connection_pool]) -> str:
    return f"connected to {pool['host']}:{pool['port']}"
```

### Multiple dependencies in one function

```python
@register_provider()
async def auth_token() -> str:
    return "secret-token"

@inject
async def api_call(
    pool: dict = Depends[connection_pool],
    token: str = Depends[auth_token],
) -> str:
    return f"pool={pool['host']}, token={token}"
```

### String-based dependency name

Use `Depends["name"]` when you want to refer to a provider by name rather than
by its function reference.  Useful for dynamic provider selection.

```python
@register_provider()
def my_config() -> dict:
    return {"value": 42}

@inject
def consumer(cfg: dict = Depends["my_config"]) -> int:
    return cfg["value"]
```

---

## Context Manager Providers (Resource Management)

Context manager providers follow the **setup / yield / teardown** pattern.  The
DI system enters the context manager, injects the yielded value, and then exits
it (running teardown) after the injected function completes.

### `context_manager=True` is required

You **must** pass `context_manager=True` to `@register_provider()` whenever
your provider is a context manager (decorated with `@asynccontextmanager`,
`@contextmanager`, or returning an `AsyncGenerator` / `Generator`).

Without this flag the provider is registered as a plain callable — the yielded
value is **never** extracted, and teardown code **never** runs.

```python
from contextlib import asynccontextmanager

# ✅ CORRECT — context manager is entered/exited by the DI system
@register_provider(context_manager=True)
@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSession(engine)
    try:
        yield session
    finally:
        await session.close()

# ❌ WRONG — without context_manager=True the generator object is injected,
#            not the yielded session, and session.close() never runs
@register_provider()
@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    ...
```

Passing `context_manager=True` on a function that is not a context manager
raises `ValueError` at registration time.

### CRITICAL: Always use `try-finally` (or `try-except`)

The DI system uses a *hybrid* cleanup strategy:
- **Success path** — calls `anext()` / `next()` to advance the generator past
  `yield`, running any code after it.
- **Exception path** — calls `athrow()` / `throw()` to inject the exception at
  the `yield` point.

Without `try-finally`, cleanup code placed *after* `yield` will **not run**
when an exception is thrown.

```python
# ✅ CORRECT — cleanup always runs
@register_provider(context_manager=True)
@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSession(engine)
    try:
        yield session
        await session.commit()   # success path
    except Exception:
        await session.rollback() # failure path
        raise
    finally:
        await session.close()    # always runs

# ❌ BROKEN — cleanup after yield won't run on exception
@register_provider(context_manager=True)
@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSession(engine)
    yield session
    await session.close()  # won't run if an exception is thrown!
```

### Async generator provider

```python
from contextlib import asynccontextmanager
from typing import AsyncGenerator

@register_provider(context_manager=True)
@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSession(engine)
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

@inject
async def fetch_user(user_id: int, session: AsyncSession = Depends[db_session]) -> User:
    return await session.get(User, user_id)
```

### Sync generator provider

```python
from contextlib import contextmanager
from typing import Generator

@register_provider(context_manager=True)
@contextmanager
def file_handle() -> Generator[IO, None, None]:
    fh = open("/tmp/data.txt")
    try:
        yield fh
    finally:
        fh.close()

@inject
def read_data(fh: IO = Depends[file_handle]) -> str:
    return fh.read()
```

### Cleanup on exceptions

Cleanup code in `finally` blocks runs even when the injected function raises:

```python
@register_provider(context_manager=True)
@asynccontextmanager
async def managed_resource() -> AsyncGenerator[Resource, None]:
    resource = await Resource.acquire()
    try:
        yield resource
    finally:
        await resource.release()  # runs even if the function below raises

@inject
async def do_work(resource: Resource = Depends[managed_resource]) -> None:
    raise ValueError("something went wrong")  # resource.release() still called
```

### Cleanup warnings

If cleanup code itself raises an exception, the DI system:
- Logs a **warning** (so you can diagnose the resource leak)
- Continues cleaning up any other generator providers
- Does **not** re-raise the cleanup exception

Check your application logs for messages like
`"Exception during cleanup of generator dependency"`.

---

## Wiring the Registry

Call `setup()` **once per process** before any `@inject`-decorated function is
called.  Typically this belongs in your application startup hook.

```python
# FastAPI
@app.on_event("startup")
async def startup():
    setup()

# Plain script
if __name__ == "__main__":
    setup()
    asyncio.run(main())
```

You can pass permanent overrides at wire time:

```python
setup(overrides={original_provider: replacement_provider})
```

See [dependency_overrides.md](./dependency_overrides.md) for full details on
all override mechanisms.

---

## Testing

### Use `@pytest.mark.skip_wire` and define providers inline

The `skip_wire` marker prevents the automatic `setup()` call (if your
`conftest.py` has one), letting you define fresh providers inside each test
and call `setup()` manually.

```python
import pytest
from cem.di import register_provider, Depends, inject, setup

@pytest.mark.skip_wire
async def test_my_feature():
    @register_provider()
    async def config() -> dict:
        return {"timeout": 5}

    @inject
    async def get_timeout(cfg: dict = Depends[config]) -> int:
        return cfg["timeout"]

    setup()

    assert await get_timeout() == 5
```

### Override providers with `provider_overrides`

`provider_overrides` is a context manager that temporarily replaces providers
for the duration of the block.  The original providers are restored afterwards.

```python
from cem.di import provider_overrides, clear_overrides

@pytest.mark.skip_wire
async def test_with_mock_config():

    @register_provider()
    async def config() -> dict:
        return {"url": "https://real.api.example.com"}

    async def fake_config() -> dict:
        return {"url": "https://fake.example.com"}

    @inject
    async def get_url(cfg: dict = Depends[config]) -> str:
        return cfg["url"]

    setup()
    clear_overrides()

    with provider_overrides({config: fake_config}):
        assert await get_url() == "https://fake.example.com"

    # Original restored
    assert await get_url() == "https://real.api.example.com"
```

### Permanently override a provider in a test

Use `override_provider` for a permanent replacement within a test, and
`clear_overrides()` to clean up afterwards.

```python
from cem.di import override_provider, clear_overrides

@pytest.mark.skip_wire
async def test_permanent_override():

    @register_provider()
    async def original() -> str:
        return "original"

    async def replacement() -> str:
        return "replaced"

    @inject
    async def get_value(val: str = Depends[original]) -> str:
        return val

    setup()

    override_provider(original, replacement)
    assert await get_value() == "replaced"

    clear_overrides()
    assert await get_value() == "original"
```

---

## Async vs Sync Constraints

| Call site | Provider type | Allowed? |
|---|---|---|
| `async` function | `async` provider | ✅ |
| `async` function | sync provider | ✅ |
| sync function (no event loop) | `async` provider | ✅ — runs in a new event loop |
| sync function (event loop running) | `async` provider | ❌ — raises `RuntimeError` |
| sync provider | `async` dependency | ❌ — raises `RuntimeError` |

When a sync function is called from within an async context (e.g. from inside
an `async` function or a running event loop) and one of its dependencies is
async, the DI system raises a clear error:

```
RuntimeError: Cannot resolve async dependency 'config' in sync function
'my_func' from within an async context.  Either make 'my_func' async or
call it from a sync context.
```

Similarly, a sync provider that declares an async dependency will raise:

```
RuntimeError: Cannot resolve async dependency 'cfg' in sync provider
'my_sync_provider'.  Sync providers cannot have async dependencies.
Make your provider async instead: async def my_sync_provider(...)
```

---

## See Also

- [dependency_overrides.md](./dependency_overrides.md) — All four override mechanisms in detail
- [dependency_injection_deployment_models.md](./dependency_injection_deployment_models.md) — ASGI/WSGI deployment scenarios
