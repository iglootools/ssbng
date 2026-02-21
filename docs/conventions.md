# Conventions

## General Coding Conventions
- **Functional Style**: Prefer functional programming style over procedural style. Use pure functions and avoid side effects when possible.
- **Charsets**: UTF-8 everywhere.
- **Time management**
  - UTC for all timestamps
  - Do not generate the current timestamps in core logic and pass from the tests and other entry points.
- **Mocks**
  - Avoid use of mocks when the values can be passed as a parameter (e.g. time)
- **Console output**
  - Do not hardcode indents in strings, compute the indent at the call site
- **Version Management**
  - Pin specific versions of all dependencies or use a lock file (e.g. poetry.lock) to ensure reproducible builds and avoid issues with breaking changes in dependencies.
  
    ```bash
    # examples
    mise use --pin pipx:poetry
    ```


## Python Conventions
- **Typing**: Use type annotations for all functions and methods, including return types. Use `mypy` for static type checking.
- **All model objects are frozen pydantic dataclasses** — immutable once created.
- **Line length**: 79 characters (black + flake8).
- **Python version**: 3.14 (mypy target and black target).
- **Control Flow**
  - Prefer match-case over if-elif-else chains
  - Prefer comprehensions and built-ins (map, filter) over manual loops when appropriate. 
  - Avoid `continue` in loops, and prefer filtering with comprehensions or built-ins instead.
  - Prefer explicit if/else syntax over implicit else 

## Application-Specific Conventions
- **Naming Conventions**
  - `kebab-case` for CLI commands and config keys
- **CLI**
  - Use `typer` for CLI implementation (argument parsing, formatting, etc.)
  - Provide both human-readable and JSON output formats for all commands, with human-readable as the default.
  - Provide ability to pass a config file to all commands
  - Provide a dry-run parameter wherever it makes sense
- **Testing**
  - No real rsync/ssh/btrfs calls in unit tests - use mocks instead. Docker-enabled integration tests cover the real interactions.
  - Generate YAML test data using the Pydantic data models and `model.model_dump()` instead of hardcoding YAML strings. 
    This ensures the test data is always valid and consistent with the models.
- **Domain logic**
  - When making changes to the config schema/models or status checks, make sure to update:
    - The `testcli` CLI app to generate new test data that reflects the changes, and update the expected outputs in `testdata.py` if necessary.
    - The `cli` CLI app to support the new functionality, and update the formatting logic in `outputs.py` if necessary.
  - When adding a dependency on an external tool (e.g. `stat`, `findfmt`), add a check for the tool in the CLI app and provide a clear error message if it's not found. 