# Dependency Override Guide

This guide explains how to override dependencies in the `cem` dependency injection system.

## Overview

The DI system provides **four methods** for overriding providers:

1. **Decorator** (`@override_provider`) - Most elegant for production overrides
2. **Pass to setup()** - Convenient for application bootstrap configuration
3. **Function call** (`override_provider()`) - Explicit programmatic overrides
4. **Context manager** (`provider_overrides()`) - Temporary overrides for testing

---

## Method 1: Decorator (Recommended)

Use [`@override_provider(original)`](../api/di.md#cem.di.override_provider) as a decorator on your replacement function.

**Best for:** Production configuration, application-level overrides

```python
from cem.di import override_provider, setup
from cem.context import context_storage_singleton, ContextStorage

class RedisContextStorage(ContextStorage):
    # ... implementation ...
    pass

# Use decorator to override
@override_provider(context_storage_singleton)
def redis_storage() -> ContextStorage:
    return RedisContextStorage()

# Call setup() - it will use Redis storage
setup()
```

**Advantages:**
- Clean, declarative syntax
- Clear intent - override is defined right at the function
- No separate function call needed

---

## Method 2: Pass to setup()

Pass overrides as a dictionary to [`setup(overrides={...})`](../api/di.md#cem.di.setup).

**Best for:** Centralizing all configuration in one place at application startup

```python
from cem.di import setup
from cem.context import context_storage_singleton, ContextStorage

class RedisContextStorage(ContextStorage):
    # ... implementation ...
    pass

def redis_storage() -> ContextStorage:
    return RedisContextStorage()

# Pass overrides to setup()
setup(overrides={
    context_storage_singleton: redis_storage,
    # Can add multiple overrides here
})
```

**Advantages:**
- All overrides visible in one place
- Good for configuration files
- Can apply multiple overrides at once

---

## Method 3: Function Call

Call [`override_provider(original, override)`](../api/di.md#cem.di.override_provider) explicitly.

**Best for:** Programmatic/dynamic overrides, conditional logic

```python
from cem.di import override_provider, setup
from cem.context import context_storage_singleton, ContextStorage

class RedisContextStorage(ContextStorage):
    # ... implementation ...
    pass

def redis_storage() -> ContextStorage:
    return RedisContextStorage()

# Explicit function call
override_provider(context_storage_singleton, redis_storage)

# Call setup() after overrides
setup()
```

**Advantages:**
- Explicit and clear
- Can be called conditionally
- Works well with dynamic configuration

---

## Method 4: Context Manager (For Testing)

Use [`provider_overrides()`](../api/di.md#cem.di.provider_overrides) context manager for temporary overrides.

**Best for:** Unit tests, temporary overrides

```python
import pytest
from uuid import UUID
from cem.di import provider_overrides, setup
from cem.context import (
    context_storage_singleton,
    InMemoryContextStorage,
)
from cem.s2.session_context import SessionContext

# Wire DI first
setup()

@pytest.fixture
def test_storage():
    """Create test storage with pre-populated data."""
    return InMemoryContextStorage()

def test_my_feature(test_storage):
    """Test using temporary storage override."""

    def get_test_storage() -> InMemoryContextStorage:
        return test_storage

    # Temporarily override for this test
    with provider_overrides({context_storage_singleton: get_test_storage}):
        # Code here uses test_storage
        result = my_function_that_uses_storage()
        assert result is not None

    # Outside the context manager, original storage is restored
```

**Advantages:**
- Automatic cleanup - original provider restored after context
- Perfect for isolated unit tests
- No side effects on other tests

---

## Complete Example: Redis Storage Override

Here's a complete example showing how to override the default in-memory context storage with Redis:

```python
import redis.asyncio as aioredis
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from pydantic import BaseModel
from cem.di import override_provider, setup
from cem.context import ContextStorage, context_storage_singleton


class RedisContextStorage(ContextStorage):
    """Distributed context storage using Redis."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis = aioredis.from_url(redis_url)

    @asynccontextmanager
    async def get_context[ContextTypeT: BaseModel](
        self, ctx_type: type[ContextTypeT], context_id: UUID
    ) -> AsyncIterator[ContextTypeT]:
        key = f"{ctx_type.__name__}:{context_id}"
        data = await self.redis.get(key)
        if not data:
            raise KeyError(f"No {ctx_type.__name__} context known for {context_id}")

        ctx = ctx_type.model_validate_json(data)
        try:
            yield ctx
        finally:
            # Save changes back to Redis
            await self.redis.set(key, ctx.model_dump_json())

    async def store_context[ContextTypeT: BaseModel](
        self, ctx_type: type[ContextTypeT], context_id: UUID, context: ContextTypeT
    ) -> None:
        key = f"{ctx_type.__name__}:{context_id}"
        await self.redis.set(key, context.model_dump_json())


# Method 1: Decorator (recommended)
@override_provider(context_storage_singleton)
def redis_storage() -> ContextStorage:
    return RedisContextStorage()

setup()
```

---

## Important Notes

### Override Functions Don't Need @register_provider

When overriding, your replacement function should be a **plain function** without the `@register_provider` decorator:

```python
# ❌ WRONG - Don't use @register_provider on overrides
@register_provider(singleton=True)
def redis_storage() -> ContextStorage:
    return RedisContextStorage()

# ✅ CORRECT - Plain function
def redis_storage() -> ContextStorage:
    return RedisContextStorage()

override_provider(context_storage_singleton, redis_storage)
```

Using `@register_provider` would register it as a separate provider instead of replacing the original.

### Order Matters

- **Decorator method:** The decorator must be applied before `setup()` is called
- **Function call method:** Call `override_provider()` before `setup()`
- **setup() method:** Pass overrides directly to `setup()`
- **Context manager:** Can be used anytime after `setup()` is called

### Multiple Overrides

You can override multiple providers:

```python
# Method 1: Multiple decorators
@override_provider(config)
def prod_config() -> Config:
    return Config(env="production")

@override_provider(context_storage_singleton)
def redis_storage() -> ContextStorage:
    return RedisContextStorage()

setup()

# Method 2: Pass multiple to setup()
setup(overrides={
    config: prod_config,
    context_storage_singleton: redis_storage,
})
```

### Clear Overrides

Use [`clear_overrides()`](../api/di.md#cem.di.clear_overrides) to remove all permanent overrides:

```python
from cem.di import clear_overrides

clear_overrides()  # Removes all overrides
```

Note: This doesn't affect overrides passed to `setup()` - those are already applied. Use this mainly in test cleanup.

---

## When to Use Each Method

| Method | Use Case | Example |
|--------|----------|---------|
| **Decorator** | Production config, clean declarative style | Override storage in production app |
| **setup() overrides** | Centralized configuration | Application bootstrap with config file |
| **Function call** | Dynamic/conditional logic | Override based on environment variable |
| **Context manager** | Unit tests, temporary changes | Test-specific storage with mock data |

---

## See Also

- [Dependency Injection Usage Guide](./di_usage.md) — Full guide on registering and injecting providers
- [Dependency Injection Deployment Models](./dependency_injection_deployment_models.md) — How DI works in different deployment scenarios
