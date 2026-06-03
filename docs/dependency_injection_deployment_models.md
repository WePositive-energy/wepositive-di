# Dependency Injection Deployment Guide

## Overview

This guide explains how to set up the `cem` dependency injection system across different web
server deployment models:

1. **ASGI servers** (FastAPI with Uvicorn, Hypercorn)
2. **WSGI servers with threads** (Flask with Gunicorn/uWSGI)
3. **Multi-process workers** (Gunicorn, uWSGI)
4. **Mixed sync/async** scenarios

---

## Understanding setup()

The `setup()` function calls `registry.wire()`, which:
- Registers all dependency providers with the DI container
- Sets up the injection infrastructure
- Must be called **once per process** (or once per worker in multi-worker setups)
- Is **NOT** called per-request

### Integration with ContextVars

The DI system uses Python's `contextvars` for request-scoped data:
- `setup()` wires the container once at startup
- ContextVars provide thread-safe and async-safe runtime data
- Each request sets its own context values
- Providers read from the current context automatically

---

## Deployment Scenario 1: Pure ASGI (FastAPI + Uvicorn)

### Architecture
- Single process or multiple worker processes
- Each request runs in an async task
- Automatic context isolation per request

### Calling setup()

```python
# main.py
from fastapi import FastAPI
from cem.di import setup

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    # Call setup() once when the app starts
    setup()
    print("Dependency injection wired")

# If using multiple workers, setup() is called once per worker process
```

### Running with Multiple Workers

```bash
# Uvicorn with 4 workers (4 processes)
uvicorn main:app --workers 4

# Each worker process:
# 1. Imports the app
# 2. Calls startup_event() -> setup() once
# 3. Handles requests with isolated contexts
```

### Setting Context for Requests

```python
import contextvars
from starlette.middleware.base import BaseHTTPMiddleware

request_context = contextvars.ContextVar('request_context', default=None)

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Set context for this async task (request)
        request_context.set({
            'request_id': request.headers.get('X-Request-ID'),
            'user_id': await get_current_user_id(request),
        })

        response = await call_next(request)
        return response

app.add_middleware(RequestContextMiddleware)
```

### Async Dependency Providers

```python
from cem.di import register_provider

@register_provider()
async def request_id() -> str:
    """Async provider reads from context."""
    ctx = request_context.get()
    return ctx['request_id'] if ctx else None

@register_provider()
async def user_service(req_id: str = Depends[request_id]) -> UserService:
    """Async provider uses other async providers."""
    return UserService(req_id)
```

**How it works:**
- Context set in middleware is visible to all async providers
- Each request (async task) has isolated context
- `setup()` is called once per worker at startup
- Request data flows through context, not function parameters

---

## Deployment Scenario 2: WSGI with Threads (Flask + Gunicorn)

### Architecture
- Multiple worker processes
- Each worker has a thread pool
- Each request runs in a thread from the pool
- Thread-local context isolation

### Calling setup()

```python
# app.py (Flask)
from flask import Flask, g
from cem.di import setup
import contextvars

app = Flask(__name__)
request_context = contextvars.ContextVar('request_context', default=None)

# Option 1: Call setup() at module level (runs once per worker)
setup()

# Option 2: Use Flask's before_first_request (deprecated in Flask 2.3+)
# @app.before_first_request
# def initialize():
#     setup()

# Option 3: Use a custom CLI command or startup hook
```

### Running with Gunicorn

```bash
# Gunicorn with 4 worker processes, 2 threads per worker
gunicorn app:app --workers 4 --threads 2

# Each worker process:
# 1. Imports app.py -> setup() called once
# 2. Creates thread pool (2 threads)
# 3. Each thread handles requests with isolated contexts
```

### Setting Context in Flask

```python
@app.before_request
def set_request_context():
    """Runs before each request, in the request's thread."""
    request_context.set({
        'request_id': request.headers.get('X-Request-ID'),
        'user_id': get_current_user_id(),
    })

@app.route('/users')
def get_users():
    # Context is set, now resolve dependencies

    # If dependencies are async, use asyncio.run()
    async def resolve():
        service = await resolve(user_service)
        return await service.get_users()

    users = asyncio.run(resolve())
    return jsonify(users)
```

### Mixed Sync/Async Providers

```python
# Sync provider (no async needed)
@register_provider()
def request_id() -> str:
    """Sync provider reads from context."""
    ctx = request_context.get()
    return ctx['request_id'] if ctx else None

# Async provider in sync web server
@register_provider()
async def user_service(req_id: str = Depends[request_id]) -> UserService:
    """Async provider can be used in sync environments."""
    return UserService(req_id)

# Usage in Flask route
def flask_route():
    # Sync code sets context
    request_context.set({"request_id": "123"})

    # Run async provider
    async def get_service():
        return await resolve(user_service)

    service = asyncio.run(get_service())
    # Async provider sees context set by sync code
```

**How it works:**
- Context set in sync code (Flask handler) is visible in async providers
- Each thread has isolated context
- `setup()` is called once per worker process (module level)
- Use `asyncio.run()` to call async providers from sync code

---

## Deployment Scenario 3: Multi-Process Workers (Gunicorn)

### Worker Lifecycle

Gunicorn creates worker processes using fork:

```
Master Process
├── Worker 1 (PID 1234)
│   ├── setup() called once
│   ├── Thread pool created
│   └── Handles requests R1, R2, R3...
├── Worker 2 (PID 1235)
│   ├── setup() called once
│   ├── Thread pool created
│   └── Handles requests R4, R5, R6...
└── Worker N...
```

### Using Post-Fork Hook

To initialize after the fork (but before handling requests):

```python
# gunicorn_config.py
from cem.di import setup

def post_fork(server, worker):
    """Called after worker process is forked."""
    print(f"Worker {worker.pid} initializing...")
    setup()
    print(f"Worker {worker.pid} ready")

# Run with: gunicorn app:app -c gunicorn_config.py
```

**When to use post_fork:**
- When you have resources that can't be shared across processes (database connections, file handles)
- When you want explicit control over worker initialization timing

### Module-Level setup()

```python
# app.py
from cem.di import setup

# Called once when module is imported (per worker process)
setup()

app = Flask(__name__)
# ... rest of app
```

**How this works:**
- Each worker process imports the module
- Module-level code runs once per process
- setup() is called once per worker automatically

---

## Deployment Scenario 4: Pre-Fork Model (uWSGI, Gunicorn Sync Workers)

### Pre-Fork Process

Pre-fork servers fork the master process after loading code:

```
1. Master loads code (setup() might be called here)
2. Master forks -> Worker 1, Worker 2...
3. Workers handle requests
```

### Lazy Initialization Pattern

To ensure `setup()` is called in each worker process:

```python
import threading

_setup_lock = threading.Lock()
_setup_done = False

def ensure_setup():
    """Call setup() exactly once per process, lazily."""
    global _setup_done
    if _setup_done:
        return

    with _setup_lock:
        if not _setup_done:
            setup()
            _setup_done = True

# In Flask
@app.before_request
def initialize_di():
    ensure_setup()
```

### Using Gunicorn's Post-Fork Hook

```python
# gunicorn_config.py
def post_fork(server, worker):
    setup()
```

---

## Deployment Scenario 5: Hybrid ASGI/WSGI (FastAPI on Gunicorn)

### Using Uvicorn Workers with Gunicorn

```bash
gunicorn app:app --worker-class uvicorn.workers.UvicornWorker --workers 4
```

### Application Setup

```python
# app.py
from fastapi import FastAPI
from cem.di import setup

app = FastAPI()

# Gunicorn will call this in each worker when using UvicornWorker
@app.on_event("startup")
async def startup():
    setup()
```

**How it works:**
1. Gunicorn creates worker processes
2. Each worker imports your app
3. UvicornWorker starts an async event loop
4. FastAPI's startup event fires -> setup() called
5. Worker handles requests with async context isolation

---

## Context Variable Behavior

### Thread-Local Nature

ContextVars are **thread-local**, not async-task-local:

| Scenario | Context Shared? | Isolation |
|----------|----------------|-----------|
| Same thread, sync functions | ✅ YES | ❌ NO |
| Same thread, async functions (await) | ✅ YES | ❌ NO |
| Same thread, sync -> async (asyncio.run) | ✅ YES | ❌ NO |
| Same thread, async -> sync | ✅ YES | ❌ NO |
| Different threads (ThreadPoolExecutor) | ❌ NO | ✅ YES |
| Different async tasks (create_task) | ⚠️ COPY | ✅ YES |
| Different processes (workers) | ❌ NO | ✅ YES |

### Test Results

From `test_contextvar_threading.py`:

```
Test: Sync -> Async Context Propagation
1. Sync handler set: SYNC-REQ-001
2. Async dependency sees: SYNC-REQ-001
Result: Async code sees context set by sync code in same thread

Test: Sync Handler + Async Dependencies
  Handler set context: REQ-1
    Provider 1 sees: REQ-1
    Provider 2 sees: REQ-1
  Dependencies resolved: provider2:REQ-1+provider1:REQ-1
Result: Sync handlers with async dependencies work correctly
```

---

## Setup Patterns Summary

### FastAPI + Uvicorn (Pure ASGI)
```python
# Setup
@app.on_event("startup")
async def startup():
    setup()

# Set context in middleware
class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_context.set({...})
        return await call_next(request)
```

### Flask + Gunicorn (WSGI)
```python
# Setup at module level
setup()

# Set context before each request
@app.before_request
def set_context():
    request_context.set({...})

# Use asyncio.run() for async providers
def route():
    result = asyncio.run(async_provider())
```

### Gunicorn Workers (Multi-Process)
```python
# Option 1: post_fork hook
# gunicorn_config.py
def post_fork(server, worker):
    setup()

# Option 2: Module-level
setup()  # At module level in app.py
```

---

## Example: Complete Flask Application

```python
# app.py
from flask import Flask, request, jsonify
import contextvars
import asyncio
from cem.di import setup, register_provider, Depends

# 1. Define context variable
request_context = contextvars.ContextVar('request_context', default=None)

# 2. Register providers
@register_provider()
def request_id() -> str:
    ctx = request_context.get()
    return ctx.get('request_id') if ctx else None

@register_provider()
async def user_service(req_id: str = Depends[request_id]) -> UserService:
    return UserService(req_id)

# 3. Call setup() once
setup()

# 4. Create Flask app
app = Flask(__name__)

# 5. Set context per request
@app.before_request
def set_request_context():
    request_context.set({
        'request_id': request.headers.get('X-Request-ID', 'default'),
    })

# 6. Use providers in routes
@app.route('/users')
def get_users():
    async def fetch():
        service = await resolve(user_service)
        return await service.get_users()

    users = asyncio.run(fetch())
    return jsonify(users)
```

---

## Example: Complete FastAPI Application

```python
# main.py
from fastapi import FastAPI, Request
import contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from cem.di import setup, register_provider, Depends

# 1. Define context variable
request_context = contextvars.ContextVar('request_context', default=None)

# 2. Register providers
@register_provider()
async def request_id() -> str:
    ctx = request_context.get()
    return ctx.get('request_id') if ctx else None

@register_provider()
async def user_service(req_id: str = Depends[request_id]) -> UserService:
    return UserService(req_id)

# 3. Create FastAPI app
app = FastAPI()

# 4. Call setup() on startup
@app.on_event("startup")
async def startup():
    setup()

# 5. Set context via middleware
class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_context.set({
            'request_id': request.headers.get('X-Request-ID', 'default'),
        })
        return await call_next(request)

app.add_middleware(RequestContextMiddleware)

# 6. Use providers in endpoints
@app.get('/users')
async def get_users(service: UserService = Depends[user_service]):
    return await service.get_users()
```

---

## Multi-Worker Deployment Examples

### Uvicorn Multi-Worker

```bash
uvicorn main:app --workers 4
```

Each worker:
1. Imports `main.py`
2. Creates FastAPI app
3. Calls `startup()` event → `setup()`
4. Handles requests with isolated contexts

### Gunicorn with Uvicorn Workers

```bash
gunicorn main:app --worker-class uvicorn.workers.UvicornWorker --workers 4
```

Each worker:
1. Gunicorn forks process
2. UvicornWorker starts event loop
3. FastAPI `startup()` event → `setup()`
4. Handles requests

### Gunicorn with Flask (Threaded)

```bash
gunicorn app:app --workers 4 --threads 2
```

Each worker:
1. Gunicorn forks process
2. Imports `app.py` → `setup()` called (module level)
3. Creates thread pool (2 threads)
4. Each thread handles requests with isolated contexts

### Gunicorn with Post-Fork Hook

```python
# gunicorn_config.py
from cem.di import setup

def post_fork(server, worker):
    setup()

# Run
# gunicorn app:app -c gunicorn_config.py --workers 4
```

Each worker:
1. Gunicorn forks process
2. Calls `post_fork()` → `setup()`
3. Handles requests

---

## See Also

- [Dependency Injection Usage Guide](./di_usage.md)
- [Dependency Override Guide](./dependency_overrides.md)
