# Scripts

Utility scripts live under [`scripts/`](../scripts/). Run them from the **project root** with the virtual environment activated so imports resolve.

## `scripts/seed_data.py`

**Purpose:** Create or **overwrite** demo JSON data under the configured data directory.

**Behavior:**

1. Resolves directory via `get_data_dir()` ([`storage.py`](../storage.py)): `FARMER_CHAT_DATA_DIR` or `./data`.
2. Hashes passwords with [`auth.hash_password`](../auth.py).
3. Writes **`farmers.json`**: one `role: admin` user (`admin` / `admin123`) plus **100 farmers** (`farmer001`–`farmer100` / shared `changeme` hash).
4. Writes **`animals.json`**: 1–3 animals per farmer with varied species/breeds.
5. Writes **empty** `health_logs.json` and `consultations.json` (`[]`).

**Warning:** Running this **replaces** existing `farmers.json` and `animals.json` and **clears** log files. Back up production data first.

**Usage:**

```bash
python scripts/seed_data.py
```

**Output:** Prints counts and default logins (farmer + admin).

---

## `scripts/add_admin_user.py`

**Purpose:** **Append** an admin account to existing `farmers.json` **without** touching farmers or animals.

**Behavior:**

1. Loads current farmers via [`load_farmers`](../storage.py).
2. If any row has `login_username` equal to `admin` (case-insensitive check in script), prints message and exits.
3. Otherwise inserts at index `0` a `Farmer` with `id=admin`, `role=admin`, username `admin`, password **`admin123`** (hashed).

**Usage:**

```bash
python scripts/add_admin_user.py
```

**Use case:** You already seeded or imported data and only need the admin row.

---

## Path setup

Both scripts prepend the repository root to `sys.path` so imports like `from auth import ...` work when executed as:

```bash
python scripts/seed_data.py
```

---

## Related

- [01 – Getting started](01-getting-started.md)
- [03 – Data models and storage](03-data-models-and-storage.md)
- [04 – Authentication and roles](04-authentication-and-roles.md)
