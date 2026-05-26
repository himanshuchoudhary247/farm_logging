# Authentication and roles

Authentication is **username and password** against rows in **`farmers.json`**. There is no OAuth, SSO, or session server in v1.

## Modules

- [`auth.py`](../auth.py) – hash and verify passwords, authenticate user.
- [`storage.py`](../storage.py) – `get_farmer_by_username`, `load_farmers`, `farmer_accounts`.

## Password hashing

- Library: **bcrypt** (direct calls, not passlib).
- `hash_password(plain)` → UTF-8 encode, `bcrypt.hashpw(..., bcrypt.gensalt())`, decode to str for JSON.
- `verify_password(plain, stored_hash)` → `bcrypt.checkpw`; invalid hash encoding returns `False`.

Passwords are **never** stored in plaintext in JSON.

## Login flow

1. User submits username and password in Streamlit [`app.py`](../app.py).
2. `authenticate(username, password)` loads farmer by **case-insensitive** username match.
3. If no row or verify fails → `None` (same error shown to user).
4. If ok → `Farmer` returned; session stores `farmer_id`, `farmer_name`, `is_admin` from `role`.

## Roles

| `Farmer.role` | Meaning |
| --------------- | ------- |
| `farmer` (default) | Normal user; data scope is their own `id`. |
| `admin` | Can log in; must pick another farmer in the sidebar to view animals, logs, and consultations. |

Admin rows should use a dedicated `id` (e.g. `admin`). They typically have **no animals** in `animals.json`; the UI scopes by the selected farmer.

## Adding or changing users

### Seed script

[`scripts/seed_data.py`](../scripts/seed_data.py) creates one admin and 100 farmers with a shared demo password for farmers (`changeme`) and a fixed admin password (`admin123`). **Replace these in production.**

### Add admin to existing data

[`scripts/add_admin_user.py`](../scripts/add_admin_user.py) inserts an admin row if username `admin` is not present.

### Manual / scripted updates

1. Generate a bcrypt hash in Python:

   ```python
   from auth import hash_password
   print(hash_password("your-new-password"))
   ```

2. Edit `farmers.json`: set `password_hash` on the right row. Keep valid JSON.

3. Ensure `login_username` is unique.

## Security notes

- Treat `farmers.json` as **sensitive**; it contains password hashes.
- Use HTTPS and strong passwords in production; see [10 – Security and operations](10-security-and-operations.md).
- Session state lives **in the browser / Streamlit server**; protect the Streamlit deployment from cross-site and network sniffing.

## Related

- [02 – Application and UI](02-application-and-ui.md) – admin farmer selector.
- [07 – Scripts](07-scripts.md) – seed and add-admin behavior.
