# Deployment

Call [`setup()`](api/di.md#wepositive_di.di.setup) once per process after all
provider modules have been imported. In multi-worker deployments, each worker
process must wire its own registry.

## Plain scripts and workers

```python
import asyncio

from wepositive_di import setup


async def main() -> None:
    ...


if __name__ == "__main__":
    setup()
    asyncio.run(main())
```

## ASGI applications

Use your framework lifespan hook.

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from wepositive_di import registry, setup


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup()
    yield
    await registry.shutdown_resources()


app = FastAPI(lifespan=lifespan)
```

Each Uvicorn or Gunicorn worker process runs the lifespan independently.

## WSGI applications

For Flask or other sync frameworks, call `setup()` at module import time or from
a worker startup hook.

```python
from flask import Flask

from wepositive_di import setup


setup()
app = Flask(__name__)
```

If sync request handlers depend on async providers, they can be resolved only
when no event loop is already running in that thread.

## Shutdown

Plain singleton providers do not need DI shutdown. Singleton context manager
providers do.

```python
from wepositive_di import registry


registry.shutdown_resources()        # sync singleton resources
await registry.shutdown_resources()  # async singleton resources
```

Match the shutdown call to the kind of resources you registered.

## Context storage in workers

The default `InMemoryContextStorage` is per process. In a multi-process
deployment, workers do not share in-memory context. Override
`context_storage_singleton` with a distributed storage implementation when
contexts must be shared across workers.
