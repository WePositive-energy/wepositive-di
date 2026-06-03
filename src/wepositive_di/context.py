from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import UUID

import aiologic
from pydantic import BaseModel

from wepositive_di.di import register_provider


class ContextStorage(ABC):
    """ContextStorage interface.

    This interface allows for different storage backends (in-memory, Redis, etc.)
    to be used for storing context data, keyed by both context type and UUID.

    One storage instance can hold multiple context types simultaneously.
    Implementations must be thread-safe and async-safe.

    get_context is an async context manager that yields the context while holding
    a lock, ensuring safe modifications during the entire usage period.
    """

    @abstractmethod
    def get_context[ContextTypeT: BaseModel](
        self, ctx_type: type[ContextTypeT], context_id: UUID
    ) -> AbstractAsyncContextManager[ContextTypeT]:
        """Get a context for the given type and context_id.

        This is an async context manager that yields the context while holding a lock.
        The lock is held until the context manager exits.

        Args:
            ctx_type: The type of context to retrieve
            context_id: The UUID identifying the context

        Yields:
            The context associated with this type and identifier

        Raises:
            KeyError: If the context does not exist
        """
        ...

    @abstractmethod
    async def store_context[ContextTypeT: BaseModel](
        self, ctx_type: type[ContextTypeT], context_id: UUID, context: ContextTypeT
    ) -> None:
        """Store a new context.

        This creates or replaces a context for the given type and context_id.
        Thread-safe and async-safe.

        Args:
            ctx_type: The type of context being stored
            context_id: The UUID identifying the context
            context: The context to store
        """
        ...

    @abstractmethod
    async def get_context_snapshot[ContextTypeT: BaseModel](
        self, ctx_type: type[ContextTypeT], context_id: UUID
    ) -> ContextTypeT:
        """Get a read-only snapshot source without taking the context lock.

        This is intended for event emission paths that must not wait behind a
        long-running mutable context lock.
        """
        ...


class InMemoryContextStorage(ContextStorage):
    """Unified in-memory storage for contexts that works in both async and threaded environments.

    Uses aiologic.RLock for synchronization, which works seamlessly across:
    - Pure async servers (FastAPI with single event loop)
    - Threaded servers with multiple threads
    - Hybrid environments (multiple threads each with their own event loop)

    Contexts are stored in a two-level dict keyed first by context type, then by UUID.
    Fine-grained per-(type, id) locking allows concurrent access to different contexts.

    Note: This implementation is single-process only. For multi-process
    deployments (e.g., gunicorn with multiple processes), consider using
    a distributed storage backend like Redis.
    """

    def __init__(self) -> None:
        self._states: dict[type[BaseModel], dict[UUID, BaseModel]] = {}
        self._locks: dict[type[BaseModel], dict[UUID, aiologic.RLock]] = {}
        self._locks_lock = aiologic.RLock()

    async def _get_lock(
        self, ctx_type: type[BaseModel], context_id: UUID
    ) -> aiologic.RLock:
        """Get or create a lock for the given (ctx_type, context_id) pair."""
        async with self._locks_lock:
            if ctx_type not in self._locks:
                self._locks[ctx_type] = {}
            if context_id not in self._locks[ctx_type]:
                self._locks[ctx_type][context_id] = aiologic.RLock()
            return self._locks[ctx_type][context_id]

    @asynccontextmanager
    async def get_context[ContextTypeT: BaseModel](  # pyright: ignore [reportReturnType]
        self, ctx_type: type[ContextTypeT], context_id: UUID
    ) -> AsyncGenerator[ContextTypeT]:
        lock = await self._get_lock(ctx_type, context_id)
        async with lock:
            type_store = self._states.get(ctx_type, {})
            if context_id not in type_store:
                raise KeyError(f"No {ctx_type.__name__} context known for {context_id}")
            yield type_store[context_id]  # pyright: ignore [reportReturnType]

    async def store_context[ContextTypeT: BaseModel](
        self,
        ctx_type: type[ContextTypeT],
        context_id: UUID,
        context: ContextTypeT,
    ) -> None:
        """Store a new context.

        Thread-safe creation/replacement of context.
        Acquires the fine-grained lock for this (ctx_type, context_id) pair.
        """
        lock = await self._get_lock(ctx_type, context_id)
        async with lock:
            if ctx_type not in self._states:
                self._states[ctx_type] = {}
            self._states[ctx_type][context_id] = context

    async def get_context_snapshot[ContextTypeT: BaseModel](
        self,
        ctx_type: type[ContextTypeT],
        context_id: UUID,
    ) -> ContextTypeT:
        type_store = self._states.get(ctx_type, {})
        if context_id not in type_store:
            raise KeyError(f"No {ctx_type.__name__} context known for {context_id}")
        context = type_store[context_id]
        return context.model_copy(deep=True)  # pyright: ignore [reportReturnType]


@register_provider(singleton=True)
def context_storage_singleton() -> InMemoryContextStorage:
    """Singleton provider for the context storage.

    Returns the same InMemoryContextStorage instance for the lifetime of the application.
    One instance can hold all context types, keyed by (type, UUID).

    This implementation uses aiologic.RLock which works seamlessly in:
    - Async servers (FastAPI): Non-blocking async synchronization
    - Threaded servers: Thread-safe synchronization
    - Hybrid environments: Multiple threads with event loops per thread

    For multi-process deployments, replace with RedisContextStorage or another
    distributed storage implementation.
    """
    return InMemoryContextStorage()
