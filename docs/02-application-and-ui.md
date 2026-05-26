# Application and UI

The user interface is a single **Streamlit** application defined in [`app.py`](../app.py). There is no separate frontend build step.

## Entry point

- **File:** [`app.py`](../app.py)
- **Command:** `streamlit run app.py`
- **Page config:** title “Farmer livestock assistant”, wide layout, cow emoji icon.

On import, the app runs `load_dotenv()` so variables from a `.env` file are available before authentication and LLM setup.

## Login gate

If `st.session_state.farmer_id` is unset, the app shows:

- Title and caption.
- A **form** with username, password, and “Log in”.
- On success: stores session fields and `st.rerun()`.
- On failure: error message (same message for unknown user and wrong password, which avoids user enumeration).

## Session state keys

| Key | Purpose |
| --- | ------- |
| `farmer_id` | Logged-in account id (`admin` or e.g. `f-001`) |
| `farmer_name` | Display name from `Farmer.name` |
| `is_admin` | `True` if `Farmer.role == "admin"` |
| `general_messages` | List of `{role, content}` for **General Q&A** |
| `triage_messages` | List for **Describe.issue** chat |
| `triage_animal_id` | Optional animal id linked to current triage thread |
| `admin_farmer_pick` | Streamlit widget key for admin farmer selector |

Logout clears these and pops `admin_farmer_pick`.

## Admin vs farmer

- **Farmer:** All data tabs use `farmer_id` as the **scope** for animals, logs, and consultations.
- **Admin:** Sidebar shows **“View / edit as farmer”** `selectbox` over `farmer_accounts()` (only `role == "farmer"`). The chosen farmer’s id is **`scope_farmer_id`**; animals and CRUD use that id, not `admin`.

If no farmer accounts exist, the admin sees an error and can only log out.

## Sidebar (after login)

- Signed-in label, with **(admin)** suffix when applicable.
- Admin farmer selector (see above).
- **Log out** button.
- Caption with effective `LLM_CONFIG_PATH` env or default path.

## Tabs

### General Q&A

- Renders `general_messages` as chat bubbles.
- `st.chat_input` sends user text; app calls `get_text_adapter().complete(...)` with **GENERAL_SYSTEM** from [`llm/prompts.py`](../llm/prompts.py).
- **Clear chat** resets `general_messages`.
- LLM adapter is cached with `@st.cache_resource` (`_text_adapter`).

### Health log

- **Search** text input filters animals by tag, species, breed substring.
- **Animal** `selectbox` on filtered list.
- **Form** fields: issue (required), appetite, feces, temperature, duration, notes.
- Submit calls `append_health_log(scope_farmer_id, animal_id, ...)`.

### Describe issue (triage chat)

- **New consultation** clears triage messages and summary widget state.
- **Link to animal (optional)** updates `triage_animal_id`.
- Chat input appends user message, calls LLM with **TRIAGE_SYSTEM**, appends assistant reply.
- **Summary** optional text field; **Save consultation** calls `append_consultation` with messages and summary.

### Records

- Filter by animal or “all”.
- **Health logs** table: id, time, animal label, issue, params string.
- **Consultations** expandable sections with full message list.

Helper **`_animal_label`** maps `animal_id` to tag/species for display.

## File references

| Concern | Module |
| ------- | ------ |
| Auth | [`auth.py`](../auth.py) |
| Persistence | [`storage.py`](../storage.py) |
| LLM | [`llm/adapters.py`](../llm/adapters.py), [`llm/prompts.py`](../llm/prompts.py) |
| Types | [`models.py`](../models.py) |

## Limitations (by design)

- Single-process Streamlit; see [10 – Security and operations](10-security-and-operations.md) for multi-worker notes.
- No built-in HTTPS; terminate TLS at a reverse proxy or load balancer in production.
- Voice block in YAML is not wired into the UI yet; see [05 – LLM](05-llm-providers-and-prompts.md).
