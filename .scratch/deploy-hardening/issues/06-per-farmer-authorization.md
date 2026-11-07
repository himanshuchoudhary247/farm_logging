# 06: Per-farmer_id authorization

**What to build:** Every route takes `farmer_id` as a path parameter with no
check that the caller is actually allowed to see that farmer's data -- any
valid API key can query any farmer's chat history, health logs, or farm
summary. Using the caller identity from ticket 05, scope each caller's key
to the specific farmer_id(s) it's allowed to touch (the UI app's key should
be allowed to act on behalf of whichever farmer is actually logged in on
its side, not every farmer in the system).

**Blocked by:** 05 (Per-caller API keys)

**Status:** ready-for-agent

- [ ] A caller's key carries (or resolves to) which farmer_id(s) it may access
- [ ] A request for a farmer_id outside that caller's allowed set is rejected (403), not silently served
- [ ] The UI app's own calling pattern (one app key, many farmers, scoped per end-user request) is explicitly supported, not just the dev/single-farmer case
- [ ] Existing tests plus new tests covering the rejection path
