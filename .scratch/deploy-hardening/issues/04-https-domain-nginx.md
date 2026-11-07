# 04: HTTPS via domain + nginx

**What to build:** The pilot currently serves every request -- including the
shared API key itself -- over plain HTTP to a raw IP (`16.4.149.68:8001`).
Anyone on the network path can read it. Stand up a real subdomain
(`assistant.flokiq.com`, matching the UI's own naming and the existing
`sandboxapi.flokiq.com` pattern), proxied through Cloudflare for automatic
edge TLS, with nginx on the box fronting the app per
`deploy/nginx-farmer-chat.conf` (already has the PR #85 `client_max_body_size`
fix baked in).

**Blocked by:** None (can start immediately -- the DNS record itself is an
external action for whoever has Cloudflare access, not a blocking ticket)

**Status:** ready-for-agent

- [ ] DNS A record added in Cloudflare: `assistant.flokiq.com` -> `16.4.149.68`, proxied
- [ ] nginx installed and configured on the box per `deploy/nginx-farmer-chat.conf`, server_name updated to the real subdomain
- [ ] `https://assistant.flokiq.com/api/healthz` (and the other endpoints under `/api/`) reachable and working end to end
- [ ] Plain `http://16.4.149.68:8001` direct access either removed from the SG or left only as a fallback, not advertised as the primary URL
- [ ] Updated handoff doc for the UI team: new base URL is `https://assistant.flokiq.com/api`
