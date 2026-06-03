# Context Management

The context module is available as `wepositive_di.context`. It defines a storage
interface for typed Pydantic models keyed by context type and UUID. The default
implementation is in-memory, async-safe, and thread-safe.

## Core API

| Object | Purpose |
| --- | --- |
| [`ContextStorage`](api/context.md#wepositive_di.context.ContextStorage) | Abstract interface for context storage backends. |
| [`InMemoryContextStorage`](api/context.md#wepositive_di.context.InMemoryContextStorage) | Default single-process storage implementation. |
| [`context_storage_singleton`](api/context.md#wepositive_di.context.context_storage_singleton) | Singleton DI provider for the default storage. |

## Store and mutate context

```python
from uuid import UUID, uuid4

from pydantic import BaseModel

from wepositive_di import Depends, context, inject


class JobContext(BaseModel):
    job_name: str
    processed: int = 0


async def create_context(
    storage: context.ContextStorage,
    context_id: UUID,
) -> None:
    await storage.store_context(
        JobContext,
        context_id,
        JobContext(job_name="nightly-import"),
    )


@inject
async def process_item(
    context_id: UUID,
    storage: context.ContextStorage = Depends[context.context_storage_singleton],
) -> int:
    async with storage.get_context(JobContext, context_id) as ctx:
        ctx.processed += 1
        return ctx.processed
```

`get_context()` is an async context manager. The in-memory implementation holds a
fine-grained lock for the selected `(context type, context id)` while the context
manager is active, so mutation is safe across async tasks and threads.

## Snapshots

Use `get_context_snapshot()` when you need a read-only copy and do not want to
wait behind a mutable context lock.

```python
snapshot = await storage.get_context_snapshot(JobContext, context_id)
```

The in-memory implementation returns a deep Pydantic copy.

## Storage lifetime

`context_storage_singleton` returns one `InMemoryContextStorage` instance per
process. This is convenient for scripts, tests, and single-process services.

For multi-process deployments, in-memory state is not shared between workers.
Override `context_storage_singleton` with a backend such as Redis, Postgres, or
another external store.

```python
from wepositive_di import context, override_provider, setup


class RedisContextStorage(context.ContextStorage):
    ...


@override_provider(context.context_storage_singleton)
def redis_context_storage() -> context.ContextStorage:
    return RedisContextStorage()


setup()
```

See [Overrides & Testing](overrides-testing.md) for all override patterns.
