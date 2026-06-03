# GitHub Copilot Instructions for wepositive-common

## Code Standards

### Type Checking
- Use strict Python type checking with pyright (configured in `pyproject.toml`)
- Use `# type: ignore[error-code]` only to ignore specific errors (don't add blank `# type: ignore` statements)
- Only use type ignore comments for external libraries, not for code in this repository
- All type hints must be compatible with pyright's strict mode

### Code Coverage
- Maintain 100% code coverage with tests
- It is acceptable to test the behavior of multiple functions that work together in a single test
- Coverage configuration is in `pyproject.toml` under `[tool.coverage.*]`

### Linting and Formatting
- Use the ruff configuration from `pyproject.toml` to format code and check linting errors
- Ruff is configured to select specific linting rules - see `[tool.ruff.lint]` in `pyproject.toml`
- Follow the configured Python target version (3.12)

### Imports
- **All imports must be at the top of the file.** Never place import statements inside functions, methods, or fixtures.
- This applies to all Python files including test files, fixtures, and conftest.py.

### Testing
- Use pytest and pytest-mock for unit tests
- Tests should be async when testing async code (pytest-asyncio is available)
- Test files are located in the `tests/` directory

### Test Quality
- Use `@pytest.mark.parametrize` to cover boundary values and multiple input cases rather than single-value tests.
- When multiple tests exercise the same function with only different input/output values, merge them into a single parametrized test. Use a tuple of strings as the first argument to `@pytest.mark.parametrize` (e.g. `("input", "expected")`), not a single comma-separated string.
- **Reuse existing fixtures.** Before constructing objects inline in a test, check conftest files and the current test module for existing fixtures. If a fixture exists for a model or object, use it. Only override the specific attributes that differ for the test case in question — do not recreate the whole object.

## Dependency Management

### Installation
```bash
poetry install --with dev,docs
poetry run pre-commit install
```

### Adding Dependencies
- Use poetry to add dependencies: `poetry add <package>`
- Use poetry to add dev dependencies: `poetry add --group dev <package>`
- Always check for security vulnerabilities before adding new dependencies

## Before Each Commit

### Required Steps
1. **Change the version number**: `poetry version prerelease`
2. **Run tests**: `poetry run pytest`
3. **Run linting and type checking**: `poetry run pre-commit run --all-files`

Note: Pre-commit hooks are configured to run automatically, but you should verify they pass before pushing.

## Pre-commit Hooks

The repository uses pre-commit hooks configured in `.pre-commit-config.yaml`:
- **ruff**: Linting and auto-fixing
- **pyright**: Type checking
- **pytest**: Tests (runs on pre-push)
- **poetry checks**: Validates `pyproject.toml` format and lock file
- **poetry-version-changed**: Ensures version is bumped before pushing

## Project Structure

- `wepositive_common/`: Main source code organized by domain
- `tests/`: Test files (unit tests and BDD tests)
- `typings/`: Custom type stubs for external libraries
- Submodules are structured by domain with their own README.md files

## Additional Notes

- Prefer functional programming over classes in Python code
- Use AWS and Terraform for deployment/devops work
- Use structlog for logging
- Use pydantic for data validation and settings management
