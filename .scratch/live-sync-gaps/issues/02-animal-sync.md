# 02: Animal sync, both directions (Chocolate <-> main_backend)

**What to build:** a farmer's animals are visible to both Chocolate and
the app, regardless of which one they were added through -- in
particular, a farmer who adds an animal in the app must be able to book
an appointment for it via Chocolate.

**Blocked by:** None (can start immediately) -- deliberately deferred
out of the live-sync gap-fixing pass this ticket came from. This is the
largest and most architecturally involved of the gaps found (new route +
auth + a real two-source merge, not a small fix), and deserves its own
planning/grilling session rather than being folded into that pass.

**Status:** ready-for-agent

## Context (found during review, verified against real code, tested live)

Confirmed in both directions by reading the code, not just by the
original report's live test:

- **Chocolate -> main_backend**: `services/animal_registration/service.py`
  states outright in a comment that `flokiq_sync` has no `create_animal()`
  and main_backend has no internal route for it. An animal registered via
  Chocolate is saved only to farmer_chat's local `data/animals.json`.
- **main_backend -> Chocolate**: `storage.py::animals_for_farmer` reads
  only the local JSON file -- no code path anywhere in farmer_chat calls
  out to main_backend for a farmer's animals.
- **Impact, confirmed live**: a farmer who adds an animal in the app
  cannot book an appointment for it through Chocolate --
  `appointment_supervisor/service.py` returns the exact message
  *"You do not have any animals registered yet, so I cannot match
  '{identifier}' to one"* (the `no_animals_registered` key) for an animal
  that genuinely exists, just not in farmer_chat's local store.

## Fix shape (settled during grilling, option (a) -- one direction first)

The reported *impact* is one-directional. Scope the first pass to just
that direction; Chocolate's own local-only registrations are a lesser
problem (the farmer still sees it in Chocolate, just not reflected in
the app yet) and can be a follow-up ticket, not bundled into this one.

1. **main_backend**: new `GET /internal/farmers/{farmerId}/animals`
   route, same `X-Internal-Api-Key` pattern as
   `/internal/farmers/{farmerId}/farm-location`
   (`src/controllers/internal/farm.controller.js` is the template).
   Returns whatever shape Chocolate's appointment/animal-registration
   flows need to match an identifier against (id, tag/name, species at
   minimum).
2. **farmer_chat**: `flokiq_sync.get_farm_animals(farmer_id)` (new),
   same best-effort/never-raise/short-TTL-cache contract as
   `get_farm_pincode`. Call sites that currently call
   `animals_for_farmer(farmer_id)` directly in the appointment and
   animal-registration flows need to merge the local list with this
   remote one (dedupe by main_backend id where both sources know the
   animal, if that's ever possible -- check whether local demo animals
   and real main_backend animals can ever collide before assuming they
   can't).
3. Second direction (Chocolate -> main_backend, `create_animal` + a
   matching internal route) stays explicitly out of scope for this
   ticket -- open a follow-up once this direction ships and is verified.

- [ ] main_backend: `GET /internal/farmers/{farmerId}/animals` route +
      controller + tests (mocked Sequelize)
- [ ] farmer_chat: `flokiq_sync.get_farm_animals`, merged into the
      appointment_supervisor and animal_registration call sites that
      read a farmer's animals today
- [ ] Decide and document the merge/dedupe behavior between local and
      remote animal lists before writing the merge code, not during
- [ ] Tests on both sides matching each repo's existing conventions
- [ ] Live-verified: an app-added animal must be bookable via Chocolate
      end to end, same repro case the original report used
      (demo-1233-style animal added in the app, booked via Chocolate)
