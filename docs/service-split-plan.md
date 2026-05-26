# Service split plan (and applied changes)

This is a pragmatic split from monolith to service-oriented deployment with minimal complexity and minimal cost impact.

## Why split this way

- Keep existing Streamlit UX unchanged.
- Extract network boundaries only where natural:
  - data/auth operations
  - LLM calls
- Preserve monolith mode for local simplicity and rollback safety.

## Target services

1. **UI service** (Streamlit, existing `app.py`)
2. **API service** (`services/api_service/main.py`)
   - login
   - list farmer accounts
   - animals, health logs, consultations CRUD (farmer-scoped)
3. **LLM service** (`services/llm_service/main.py`)
   - single `chat/complete` endpoint
   - wraps provider config + adapter logic

## Migration strategy

### Phase 1 (implemented now)

- Add `gateways.py` abstraction in UI.
- Keep default mode as monolith.
- Add service mode via env:
  - `APP_MODE=services`
  - `API_SERVICE_URL`
  - `LLM_SERVICE_URL`
- Implement FastAPI services with matching behavior.

### Phase 2 (recommended next)

- Add auth token between UI and API service (currently trusted internal network).
- Add request/response validation contracts package.
- Add integration tests for service mode.

### Phase 3 (optional scale)

- Move JSON storage to managed DB/object storage.
- Add queue/worker for heavy LLM workflows if needed.

## What changed in code

- Added `gateways.py` for monolith vs service routing.
- Added `services/api_service/main.py`.
- Added `services/llm_service/main.py`.
- Updated `app.py` to call gateway functions.
- Added dependencies: `fastapi`, `uvicorn`, `requests`.
- Updated root `README.md` with service mode run commands.

## Run modes

### Monolith mode (default)

```bash
streamlit run app.py
```

### Service mode

```bash
uvicorn services.api_service.main:app --host 0.0.0.0 --port 8001
uvicorn services.llm_service.main:app --host 0.0.0.0 --port 8002
APP_MODE=services API_SERVICE_URL=http://localhost:8001 LLM_SERVICE_URL=http://localhost:8002 streamlit run app.py
```

## Cost note

For cost-sensitive deployments, keep all three processes on one small EC2 first. Split to separate hosts only when needed.
