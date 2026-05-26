# `pytest.ini` reference

[`pytest.ini`](../pytest.ini) configures **pytest** for this repository.

## Typical contents

```ini
[pytest]
pythonpath = .
testpaths = tests
```

## `pythonpath = .`

Adds the **repository root** to `sys.path` so test modules can `import storage`, `import models`, etc. without installing the project as a package.

## `testpaths = tests`

Restricts default test discovery to the [`tests/`](../tests/) directory.

## Running tests

From repo root:

```bash
pytest
```

See [08 – Testing](08-testing.md) for what the suite covers and how `FARMER_CHAT_DATA_DIR` is used in tests.

## Related

- [`tests/test_storage.py`](../tests/test_storage.py)
