# flokiq_sync — local test loop for the flokiq DB integration

Verified end-to-end 2026-09-16. Lets us test INSERT/UPSERT payloads and
real constraint behavior (species enum, doctorId/addedByUserId FKs)
against flokiq's actual schema, entirely locally — zero risk to the shared
sandbox, zero real farmer data involved.

## Pieces

- `docker-compose.yml` — disposable MySQL 8 container, auto-loads
  `data/flokiq_mirror_schema.sql` on first start (schema only, no data —
  the 6 tables farmer_chat's voice pipeline actually touches:
  `users → farmers → farms → animals → health_logs → appointments`).
- `mock_server.py` — FastAPI app backed by that container, implementing
  `POST /appointments` (real endpoint, matches `flokiquser/src/lib/apis.ts`
  exactly) and `POST /health-logs` (**proposed** — flokiquser's frontend
  has no health-log creation call at all today, only a GET to fetch one).

## Run it

```bash
docker compose -f services/flokiq_sync/docker-compose.yml up -d
# no docker-compose plugin? equivalent manual command:
#   docker run -d -e MYSQL_ROOT_PASSWORD=localtest -e MYSQL_DATABASE=flokiq_mirror \
#     -p 3399:3306 -v $(pwd)/data/flokiq_mirror_schema.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro mysql:8

uvicorn services.flokiq_sync.mock_server:app --port 8077
```

Then point whatever's testing the integration at `http://localhost:8077`
instead of the real sandbox.

## What's been proven against this, live

- Full insert chain (user → farmer → farm → animal → appointment →
  health_log) succeeds with realistic payloads.
- `species='cow'` on `animals` is rejected — `ERROR 1265: Data truncated
  for column 'species'` — confirms live the enum really is
  `('sheep','goat')` only, not a misreading of the dump.
- Both mock endpoints tested via real HTTP calls, real INSERTs landed in
  the mirror DB.

## Still needed before this is a real integration, not just a test rig

- The actual `services/flokiq_sync/client.py` adapter that farmer_chat's
  `appointment_supervisor.submit()` calls — not built yet, this is the
  test harness it'll be tested against.
- Auth: how farmer_chat gets a valid token for the outbound call to real
  flokiq — still an open question for the flokiq/mobile team.
- The real `doctorId`/`addedByUserId` placeholder `users` row — needs
  flokiq's team to create it in the actual sandbox (spec already written,
  see prior conversation) — the mirror DB here just proves the shape works,
  doesn't create anything in the real sandbox.
- `POST /health-logs` doesn't exist on the real flokiq backend — this repo
  can propose the contract (which is what `mock_server.py` does), but
  flokiq's team has to actually build it.
