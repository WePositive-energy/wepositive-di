# Overrides & Testing

Provider overrides replace a registered provider with another implementation.
They are useful for tests, local development, and deployment-specific wiring.

## Override methods

| Method | Best for |
| --- | --- |
| `@override_provider(original)` | Declarative application-level overrides. |
| `override_provider(original, replacement)` | Programmatic or conditional overrides. |
| `setup(overrides={...})` | Centralized bootstrap configuration. |
| `provider_overrides({...})` | Temporary overrides, especially tests. |

Override functions should be plain callables. Do not decorate the replacement
with `@register_provider()`.

Overrides preserve the lifecycle of the original provider. If the original
provider is registered as a singleton, the replacement is also cached as a
singleton. If the original provider is registered as a context manager, the
replacement is also entered and exited as a context manager.

## Decorator override

```python
from wepositive_di import override_provider, setup


@override_provider("settings")
def test_settings() -> dict[str, str]:
    return {"env": "test"}


setup()
```

## Setup-time override

```python
from wepositive_di import setup


def production_settings() -> dict[str, str]:
    return {"env": "production"}


setup(overrides={"settings": production_settings})
```

## Temporary override

```python
from wepositive_di import Depends, inject, provider_overrides


def fake_settings() -> dict[str, str]:
    return {"env": "test"}


@inject
def read_env(cfg: dict[str, str] = Depends["settings"]) -> str:
    return cfg["env"]


with provider_overrides({"settings": fake_settings}):
    assert read_env() == "test"
```

The previous override state is restored when the context manager exits.

## Test isolation

Tests should use an isolated DI registry so each test sees only providers it
defines itself, plus any providers explicitly created by fixtures. A small
`wire_providers` fixture can wrap `setup()` when a test needs to wire providers
with overrides.

```python
from wepositive_di import Depends, inject, register_provider, setup


async def test_injected_value(wire_providers) -> None:
    @register_provider()
    async def value() -> int:
        return 42

    @inject
    async def consumer(result: int = Depends[value]) -> int:
        return result

    wire_providers()

    assert await consumer() == 42
```

Use [`clear_overrides()`](api/di.md#wepositive_di.di.clear_overrides) in cleanup
when a test applies permanent overrides.
