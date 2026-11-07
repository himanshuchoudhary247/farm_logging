# 05: Per-caller API keys

**What to build:** Today `FARMER_CHAT_API_KEY` is one shared secret string
compared against every request's `X-Api-Key` header
(`services/api_service/main.py::require_api_key`). No per-dev or per-app
attribution, no way to revoke one caller without breaking everyone, no
rate limiting. Replace the single-key check with a small set of named keys
(e.g. `ui-app`, `dev-himanshu`, `dev-<name>`), each individually revocable,
each with a basic request-rate cap.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `require_api_key` resolves the incoming `X-Api-Key` to a named caller identity instead of a single pass/fail boolean
- [ ] Revoking one caller's key does not affect any other caller
- [ ] A basic per-key rate limit is enforced (requests/minute), configurable per key
- [ ] Existing single-key deployments keep working unchanged (backward compatible default) until migrated
