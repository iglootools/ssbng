# Building and Testing

The unit tests cover the core logic of the tool, while the integration tests exercise the real rsync/SSH/btrfs pipeline against a Docker container.

Integration tests exercise the real rsync/SSH/btrfs pipeline against a Docker container.

Run automated tests and checks (no external dependencies):
```bash
# Makefile syntax
make check              # Run all checks: format + lint + type-check + unit tests
make test               # Unit tests only (no Docker)
make test-integration   # Integration tests only (requires Docker)
make test-all           # Unit + integration tests
make format             # black
make lint               # flake8
make type-check         # mypy (strict: disallow_untyped_defs)

# Using Poetry syntax directly
poetry run pytest tests/ --ignore=tests/integration/ -v                 # Unit tests only (no Docker)
poetry run pytest tests/integration/ -v                                 # Integration tests only (requires Docker)
poetry run pytest tests/ -v                                             # Unit + integration tests
poetry run black .                                                      # formatting
poetry run flake8 ssb/ tests/                                           # linting
poetry run mypy ssb/ tests/                                             # type-checking
poetry run pytest tests/test_ssh.py::TestBuildSshBaseArgs::test_full -v # run a single test
```

The integration test suite uses [testcontainers](https://testcontainers-python.readthedocs.io/) and automatically:
- Generates an ephemeral SSH key pair
- Builds and starts a Docker container with SSH, rsync, and a btrfs filesystem
- Runs tests covering local-to-local, local-to-remote, remote-to-local syncs, btrfs snapshots, and status checks
- Tears down the container on completion