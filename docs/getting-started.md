# Getting Started

Install the package and call `setup()` once after your providers are imported.

```bash
pip install wepositive-di
```

## Basic dependency injection

```python
import asyncio

from wepositive_di import Depends, inject, register_provider, setup


@register_provider()
def settings() -> dict[str, str]:
    return {"api_base_url": "https://api.example.com"}


@register_provider()
async def api_client(cfg: dict[str, str] = Depends[settings]) -> str:
    return f"client for {cfg['api_base_url']}"


@inject
async def handle_message(client: str = Depends[api_client]) -> str:
    return client


setup()

print(asyncio.run(handle_message()))
```

`Depends[settings]` and `Depends[api_client]` mark parameters that should be
resolved by the DI container. The decorated function can still accept normal
arguments; only parameters with `Depends[...]` defaults are injected.

## Resource providers

Use `context_manager=True` for dependencies that need setup and teardown around
each injected call.

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from wepositive_di import Depends, inject, register_provider


@register_provider(context_manager=True)
@asynccontextmanager
async def session() -> AsyncGenerator[dict[str, bool], None]:
    resource = {"open": True}
    try:
        yield resource
    finally:
        resource["open"] = False


@inject
async def do_work(db: dict[str, bool] = Depends[session]) -> bool:
    return db["open"]
```

## Context storage

The context package is available as `wepositive_di.context` and provides a
default in-memory context storage singleton. A common pattern is to keep the
current context id in a `ContextVar`, then expose the current typed context as a
DI provider.

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from uuid import uuid4

from pydantic import BaseModel

from wepositive_di import Depends, context, inject, register_provider, setup


class MessageContext(BaseModel):
    message_id: str
    attempts: int = 0


current_context_id: ContextVar = ContextVar("current_context_id")


@register_provider()
@asynccontextmanager
async def current_message_context(
    storage: context.ContextStorage = Depends[context.context_storage_singleton],
) -> AsyncGenerator[MessageContext]:
    async with storage.get_context(MessageContext, current_context_id.get()) as ctx:
        yield ctx


@inject
async def increment_attempts(
    message_context: MessageContext = Depends[current_message_context],
) -> int:
    message_context.attempts += 1
    return message_context.attempts


@inject
async def handle_message(
    context_id,
    storage: context.ContextStorage = Depends[context.context_storage_singleton],
) -> int:
    await storage.store_context(
        MessageContext,
        context_id,
        MessageContext(message_id=str(context_id)),
    )
    token = current_context_id.set(context_id)
    try:
        return await increment_attempts()
    finally:
        current_context_id.reset(token)


setup()

result = await handle_message(uuid4())
```

For read-only access, a provider can use `get_context_snapshot()` instead of
holding the mutable `get_context()` lock:

```python
@register_provider()
async def current_message_snapshot(
    storage: context.ContextStorage = Depends[context.context_storage_singleton],
) -> MessageContext:
    return await storage.get_context_snapshot(
        MessageContext,
        current_context_id.get(),
    )
```

See [Context Management](context-management.md) for storage semantics and custom
backend guidance.
