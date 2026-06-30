from collections.abc import Callable
from uuid import uuid4

import pytest
from pydantic import BaseModel

from wepositive_di.context import (
    ContextStorage,
    InMemoryContextStorage,
    context_storage_singleton,
)
from wepositive_di.di import Depends, inject, setup


class ExampleContext(BaseModel):
    value: int
    nested: list[int]


class OtherExampleContext(BaseModel):
    value: str


async def test_in_memory_context_storage_stores_locks_and_mutates_context() -> None:
    storage = InMemoryContextStorage()
    context_id = uuid4()

    await storage.store_context(
        ExampleContext, context_id, ExampleContext(value=1, nested=[])
    )
    await storage.store_context(
        ExampleContext, uuid4(), ExampleContext(value=99, nested=[])
    )

    async with storage.get_context(ExampleContext, context_id) as context:
        context.value += 1
        context.nested.append(2)

    snapshot = await storage.get_context_snapshot(ExampleContext, context_id)

    assert snapshot == ExampleContext(value=2, nested=[2])


async def test_in_memory_context_storage_snapshot_is_deep_copy() -> None:
    storage = InMemoryContextStorage()
    context_id = uuid4()

    await storage.store_context(
        ExampleContext, context_id, ExampleContext(value=1, nested=[1])
    )

    snapshot = await storage.get_context_snapshot(ExampleContext, context_id)
    snapshot.nested.append(2)

    unchanged = await storage.get_context_snapshot(ExampleContext, context_id)
    assert unchanged.nested == [1]


async def test_in_memory_context_storage_deletes_context() -> None:
    storage = InMemoryContextStorage()
    context_id = uuid4()

    await storage.store_context(
        ExampleContext, context_id, ExampleContext(value=1, nested=[])
    )

    await storage.delete_context(ExampleContext, context_id)

    with pytest.raises(KeyError, match="No ExampleContext context known"):
        await storage.get_context_snapshot(ExampleContext, context_id)


async def test_in_memory_context_storage_delete_removes_lock() -> None:
    storage = InMemoryContextStorage()
    context_id = uuid4()

    await storage.store_context(
        ExampleContext, context_id, ExampleContext(value=1, nested=[])
    )
    assert context_id in storage._locks[ExampleContext]  # pyright: ignore[reportPrivateUsage]

    await storage.delete_context(ExampleContext, context_id)

    assert ExampleContext not in storage._states  # pyright: ignore[reportPrivateUsage]
    assert ExampleContext not in storage._locks  # pyright: ignore[reportPrivateUsage]


async def test_in_memory_context_storage_delete_only_removes_requested_type() -> None:
    storage = InMemoryContextStorage()
    context_id = uuid4()

    await storage.store_context(
        ExampleContext, context_id, ExampleContext(value=1, nested=[])
    )
    await storage.store_context(
        OtherExampleContext, context_id, OtherExampleContext(value="kept")
    )

    await storage.delete_context(ExampleContext, context_id)

    with pytest.raises(KeyError, match="No ExampleContext context known"):
        await storage.get_context_snapshot(ExampleContext, context_id)
    assert await storage.get_context_snapshot(
        OtherExampleContext, context_id
    ) == OtherExampleContext(value="kept")


async def test_in_memory_context_storage_delete_keeps_other_contexts_of_same_type() -> None:
    storage = InMemoryContextStorage()
    deleted_context_id = uuid4()
    kept_context_id = uuid4()

    await storage.store_context(
        ExampleContext, deleted_context_id, ExampleContext(value=1, nested=[])
    )
    await storage.store_context(
        ExampleContext, kept_context_id, ExampleContext(value=2, nested=[3])
    )

    await storage.delete_context(ExampleContext, deleted_context_id)

    with pytest.raises(KeyError, match="No ExampleContext context known"):
        await storage.get_context_snapshot(ExampleContext, deleted_context_id)
    assert await storage.get_context_snapshot(
        ExampleContext, kept_context_id
    ) == ExampleContext(value=2, nested=[3])


async def test_in_memory_context_storage_can_store_same_id_after_delete() -> None:
    storage = InMemoryContextStorage()
    context_id = uuid4()

    await storage.store_context(
        ExampleContext, context_id, ExampleContext(value=1, nested=[])
    )
    await storage.delete_context(ExampleContext, context_id)
    await storage.store_context(
        ExampleContext, context_id, ExampleContext(value=2, nested=[3])
    )

    assert await storage.get_context_snapshot(
        ExampleContext, context_id
    ) == ExampleContext(value=2, nested=[3])


async def test_in_memory_context_storage_raises_for_unknown_context() -> None:
    storage = InMemoryContextStorage()
    context_id = uuid4()

    with pytest.raises(KeyError, match="No ExampleContext context known"):
        async with storage.get_context(ExampleContext, context_id):
            pass

    with pytest.raises(KeyError, match="No ExampleContext context known"):
        await storage.get_context_snapshot(ExampleContext, context_id)

    with pytest.raises(KeyError, match="No ExampleContext context known"):
        await storage.delete_context(ExampleContext, context_id)


async def test_context_storage_singleton_provider_is_injectable(
    context_storage_provider: Callable[[], InMemoryContextStorage],
) -> None:
    _ = context_storage_provider
    @inject
    async def get_storage(
        storage: ContextStorage = Depends[context_storage_singleton],
    ) -> ContextStorage:
        return storage

    setup()

    first = await get_storage()
    second = await get_storage()

    assert isinstance(first, InMemoryContextStorage)
    assert first is second
