# 07: Wire the cron into boot + env docs

**What to build:** the weather-cache refresh job runs automatically every
4 hours once main_backend boots, and the new env vars are documented.

**Blocked by:** 05

**Implements:** [ADR 0003](../../../docs/ADR/0003-weather-cache-ownership-main-backend.md)

**Status:** ready-for-agent

- [ ] `src/controllers/weather/weatherCache.cron.js::weatherCacheRefreshCron()`,
      `cron.schedule('0 */4 * * *', ...)`, same try/catch-log shape as
      `vaccinationCron`
- [ ] Wired into `src/app.js` alongside the existing `Crons.*()` calls
- [ ] `.env.example` documents `FARMER_CHAT_API_BASE_URL`/`FARMER_CHAT_API_KEY`
- [ ] Manual check: invoking the job function runs a real tick end to end
