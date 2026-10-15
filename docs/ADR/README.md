# Architecture Decision Records

Lightweight ADRs (context / decision / consequences) for decisions that are
expensive to re-derive later -- not a full design doc, just enough that a
future reader does not re-litigate a choice without knowing why it was made.

Kept in this repo even when the implementation lands elsewhere (main_backend,
flokiquser), because this is where the chain of reasoning started and where
this project's docs already live.

| ADR | Decision |
| --- | -------- |
| [0001](0001-per-farmer-weather-report-source.md) | Per-farmer weather short report sources from farmer_chat's `/weather/alert`, not a second Open-Meteo integration |
| [0002](0002-weather-cache-key-grid-clustering.md) | Weather cache key is a coarse lat/lng grid cell, not raw PIN or raw lat/lng |
| [0003](0003-weather-cache-ownership-main-backend.md) | The 4h refresh scheduler and in-memory cache live in main_backend, not farmer_chat |
| [0004](0004-weather-alert-endpoint-auth.md) | farmer_chat's `/weather/alert` requires `FARMER_CHAT_API_KEY` before main_backend calls it on a schedule |
| [0005](0005-farm-weather-endpoint-pin-first.md) | main_backend's `GET /weather` resolves the farmer's PIN first, falling back to client-supplied lat/lng only when no PIN is on file |
