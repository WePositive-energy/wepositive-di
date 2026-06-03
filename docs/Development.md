# Development

This file collects the day-to-day commands for working on the project. All commands below use Poetry.

## Install and set up

```bash
poetry install
cp .env.example .env
poetry run pre-commit install
```

## Frontend dependencies

Use your preferred Node version manager, such as [nvm](https://github.com/nvm-sh/nvm) or
[asdf](https://asdf-vm.com/), to install Node.js. Then enable Corepack and install the frontend
dependencies:

```bash
corepack enable
yarn install
```

If Yarn version resolution fails, prefix Yarn commands with Corepack, for example:

```bash
corepack yarn build
```

## Environment configuration

Runtime configuration is read from `.env` and `.env.docker`. Start by copying `.env.example`:

```bash
cp .env.example .env
```

The example file is a template, not a guaranteed working local configuration. For the Docker-based demo,
make sure the Postgres values are uncommented and match the database URI:

```dotenv
SQLALCHEMY_DB_URI="postgresql+asyncpg://postgres:<your-password>@localhost:5434/cem"
POSTGRES_PORT=5434
POSTGRES_USER=postgres
POSTGRES_DB=cem
POSTGRES_PASSWORD=<your-password>
```

| Variable | Description |
|----------|-------------|
| `ENVIRONMENT` | Runtime environment. Use `DEVELOPMENT` locally so development-only defaults, such as permissive CORS, are enabled. |
| `LOG_LEVEL` | Default log level for the application. |
| `LOGGERS` | JSON object with per-logger log-level overrides, for example `{"uvicorn": "DEBUG"}`. |
| `SQLALCHEMY_DB_URI` | Async SQLAlchemy database URL used by the app and migrations. For Docker, the password and port must match `POSTGRES_PASSWORD` and `POSTGRES_PORT`. |
| `FASTAPI_ROOT_PATH` | Optional URL prefix when the app is served behind a proxy under a sub-path. Usually leave unset locally. |
| `POSTGRES_PORT` | Host port exposed by the Docker Postgres service. Must match the port in `SQLALCHEMY_DB_URI` when using Docker. |
| `POSTGRES_USER` | User created by the Docker Postgres service. Must match the user in `SQLALCHEMY_DB_URI`. |
| `POSTGRES_DB` | Database created by the Docker Postgres service. Must match the database name in `SQLALCHEMY_DB_URI`. |
| `POSTGRES_PASSWORD` | Password for the Docker Postgres service. Must match the password in `SQLALCHEMY_DB_URI`. |
| `AWS_ENDPOINT_URL` | AWS-compatible endpoint. Use `http://localhost:4000` for the local Moto server. |
| `AWS_REGION` | AWS region used for SNS clients. Any consistent region works with Moto. |
| `S2_MESSAGES_TOPIC_ARN` | SNS topic ARN where outbound S2 message events are published. The example FIFO ARN works with the local Moto server. |
| `TRUSTED_ISSUERS` | JSON map of trusted issuer names to public keys. Replace the placeholder before using real signed tokens. |
| `BASIC_AUTH_CREDENTIALS` | JSON map of username/password pairs for websocket basic auth in local/demo setups. Replace the example values for any shared environment. |
| `COMMUNITY_MANAGEMENT_SERVICE_BASE_URL` | Base URL for the community-management service if integrations need it. |
| `BROADCAST_URL` | Broadcast backend URL. `memory://` is suitable for local development. |
| `FASTAPI_PORT` | Port used by `poetry run serve dev` / `poetry run serve prod`. |
| `ENABLE_WEBSOCKET_BASIC_AUTH` | Enables basic auth on websocket connections when set to `true`. |

## Run tests

```bash
poetry run pytest
```

Run the full quality checks with:

```bash
poetry run pre-commit run --all-files
```

## Make migrations

Create an Alembic migration from model changes:

```bash
poetry run alembic revision --autogenerate -m "<description>"
```

## Typecheck

```bash
poetry run pyright
```

## Lint

```bash
poetry run ruff check
```

## Build and serve docs

Build the documentation site:

```bash
poetry run mkdocs build
```

Serve the documentation locally:

```bash
poetry run mkdocs serve
```

## Run the app

Start the demo/dev stack:

```bash
cp .env.example .env
docker compose up -d
poetry run db migrate
poetry run serve dev
```

`docker compose up -d` starts the local database and Moto server. `poetry run serve dev` starts the FastAPI app and frontend watchers.
`poetry run serve dev` also creates the local SNS topic in Moto automatically.

When the app is running, the automated FastAPI API docs are available at
[http://127.0.0.1:8003/docs](http://127.0.0.1:8003/docs). The OpenAPI schema is available at
[http://127.0.0.1:8003/openapi.json](http://127.0.0.1:8003/openapi.json).

For a native Postgres setup:

```bash
poetry run db setup
poetry run serve dev
```

## Build the frontend

```bash
yarn build
```

## Run in Docker

Create a `.env.docker` file for container-specific settings, or pass settings with `docker run -e`.
Do not publish secrets in this file.

```bash
docker build -f Dockerfile . -t cem:latest
docker run -p 8000:8000 -it cem:latest
```

## Versioning

Before merging release changes, bump the package version:

```bash
poetry version prerelease
```
