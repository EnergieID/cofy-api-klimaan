# cofy-api-klimaan

[cofy-api](https://github.com/EnergieID/cofy-api) instance for Klimaan, serving a solar directive: a signal that
says how good a moment is to consume electricity, based on how much solar production Elia predicts.


## Quick start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your values
```

### 3. Run the dev server

```bash
poe dev          # starts FastAPI with auto-reload, reads .env
```

The API is now available at `http://localhost:8000`.
Health-check: `GET /health`

### 4. Run a production-like container locally

```bash
poe prod         # builds the Docker image and runs it on port 8080
```

The container is available at `http://localhost:8080`.
Health-check: `GET /health`

## Development

### Code quality (pre-commit)

Pre-commit hooks are configured out of the box. Install them once:

```bash
pre-commit install
```

Every commit will automatically run:

| Tool | Task | Command |
|------|------|---------|
| **Ruff** | Linting + auto-fix | `poe lint` |
| **Ruff** | Formatting | `poe format` |
| **ty** | Type checking | `poe check` |

Run the tests with `poe test`.

You can also run them manually at any time.

## License

[MIT](LICENSE)
