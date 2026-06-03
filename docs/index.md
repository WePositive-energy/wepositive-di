# WePositive DI

WePositive DI is a small dependency injection layer on top of
[`dependency-injector`](https://python-dependency-injector.ets-labs.org/) with
FastAPI-style dependency declarations that can be used in any Python
application.

It has two parts:

| Part | Purpose |
| --- | --- |
| Dependency injection | Register sync, async, factory, singleton, and context manager providers, then inject them with `Depends[...]`. |
| Context management | Store typed Pydantic context objects in an async-safe storage backend and expose the storage through DI. |

## Why use it?

- Use the same dependency patterns in scripts, workers, web apps, and tests.
- Keep dependencies explicit without passing every object through every call.
- Manage resources with context manager providers that clean up after each call.
- Swap implementations with provider overrides for tests or deployment-specific storage.

## Start here

Read [Getting Started](getting-started.md) for a short working example, then use
[Providers](providers.md) for the full provider matrix and [API Reference](api/di.md)
for exact signatures.
