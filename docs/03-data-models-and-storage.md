# Data models and storage

The app persists **farmer, animal, health log, and consultation** data as **JSON arrays** on disk. There is no SQL database in v1.

## Data directory

- **Default path:** [`data/`](../data/) next to [`storage.py`](../storage.py) (project root).
- **Override:** set environment variable `FARMER_CHAT_DATA_DIR` to an absolute or user-expanded path.

All file paths are resolved in `get_data_dir()` in [`storage.py`](../storage.py).

## Files

| File | Contents |
| ---- | -------- |
| `farmers.json` | Array of farmer objects (includes optional `role` for admin). |
| `animals.json` | Array of animals; each has `farmer_id`. |
| `health_logs.json` | Array of structured health records from the **Health log** form. |
| `consultations.json` | Array of saved **Describe issue** chat sessions. |

The `data/` folder is intended to be **gitignored** for real deployments; use `scripts/seed_data.py` to recreate demo data locally.

## Pydantic models

Defined in [`models.py`](../models.py):

### `Farmer`

| Field | Type | Notes |
| ----- | ---- | ----- |
| `id` | str | Stable id, e.g. `f-001`, `admin` |
| `name` | str | Display name |
| `login_username` | str | Unique login; matched case-insensitively |
| `password_hash` | str | bcrypt hash, never plain text |
| `phone` | str | Optional |
| `role` | `"farmer"` \| `"admin"` | Default `"farmer"` if omitted in JSON |

### `Animal`

| Field | Type |
| ----- | ---- |
| `id` | str |
| `farmer_id` | str |
| `species` | str |
| `tag_or_name` | str |
| `breed` | str (default `""`) |
| `age_years` | float or null |

### `HealthLog`

| Field | Type |
| ----- | ---- |
| `id` | str (UUID) |
| `farmer_id` | str |
| `animal_id` | str |
| `recorded_at` | ISO 8601 UTC string |
| `issue` | str |
| `params` | object (e.g. appetite, feces, temperature) |
| `notes` | str |

### `Consultation`

| Field | Type |
| ----- | ---- |
| `id` | str |
| `farmer_id` | str |
| `animal_id` | str or null |
| `started_at` | ISO string |
| `messages` | list of `ChatMessage` |
| `status` | `"draft"` \| `"saved"` (saved on persist) |
| `summary` | str |

### `ChatMessage`

| Field | Type |
| ----- | ---- |
| `role` | `"user"` \| `"assistant"` \| `"system"` |
| `content` | str |

Only `user` and `assistant` messages are stored on consultation save.

## Storage API (summary)

Implemented in [`storage.py`](../storage.py):

- **Read:** `load_farmers`, `load_animals`, `load_health_logs`, `load_consultations` (plus filtered helpers).
- **Auth helpers:** `get_farmer_by_username`, `farmer_accounts` (farmers only).
- **Write:** `append_health_log`, `append_consultation` (append-only; IDs generated with `uuid.uuid4()`).
- **Validation:** `ensure_farmer_animal`; append functions reject animals not owned by the given `farmer_id`.

## Concurrency and durability

### File locking

Writes to `health_logs.json` and `consultations.json` run under a **`filelock`** named `<file>.lock` so two processes do not interleave read-modify-write incorrectly.

### Atomic writes

`atomic_write_json` writes to a **`.tmp`** sibling file, then **`os.replace`** into the final path so readers rarely see half-written JSON.

## Consultations JSON shape

`load_consultations` returns **raw dicts** (not always re-validated as `Consultation`) for simplicity in the Records UI; new rows are produced with `Consultation.model_dump()`.

## Related documentation

- [04 – Authentication](04-authentication-and-roles.md) – how farmer rows connect to login.
- [07 – Scripts](07-scripts.md) – how seed data populates these files.
- [08 – Testing](08-testing.md) – tests point storage at a temp directory.
