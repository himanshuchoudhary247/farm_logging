# Testing

The project uses **pytest** for a small suite focused on **storage** correctness.

## Configuration

[`pytest.ini`](../pytest.ini) at repo root:

- `pythonpath = .` — allows `import storage` and `import models` without installing a package.
- `testpaths = tests`

## Running tests

```bash
pytest
# or
pytest tests/ -q
```

Activate the project virtual environment first.

## What is tested

[`tests/test_storage.py`](../tests/test_storage.py):

1. **`test_append_health_log_scoped`**  
   - Sets `FARMER_CHAT_DATA_DIR` to a temporary directory (via `monkeypatch` + `importlib.reload(storage)`).  
   - Writes minimal `farmers.json` and `animals.json`.  
   - Asserts a valid append for matching `farmer_id` / `animal_id`.  
   - Asserts `ValueError` when the animal belongs to another farmer.  
   - Asserts `health_logs_for_farmer` isolation.

2. **`test_atomic_write_json`**  
   - Verifies JSON round-trip after `atomic_write_json`.

## Temporary data directory

Tests **must** reload `storage` after setting `FARMER_CHAT_DATA_DIR` so `get_data_dir()` picks up the new environment variable. The shared fixture `storage_mod` in `test_storage.py` handles this.

## Adding tests

- Prefer **temp dirs** and env overrides; do not rely on committed `data/` for tests.
- For LLM adapters, use mocks or integration tests behind a marker if you add them later (not required in v1).

## Related

- [03 – Data models and storage](03-data-models-and-storage.md)
- [01 – Getting started](01-getting-started.md)
