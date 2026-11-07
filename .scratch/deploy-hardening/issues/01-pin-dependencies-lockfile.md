# 01: Pin dependencies with a lockfile

**What to build:** `requirements.txt` today only declares floors (`>=`), so a
fresh install can silently pull a newer transitive dependency than the one
actually tested -- this already caused a real incident during the pilot
deploy (a newer `litellm`, pulled in by `google-adk[extensions]`, hard-imported
a `mcp` package nothing declared). Generate a frozen lockfile of exact
versions from a known-good install, and add a CI check that fails when
`requirements.txt` and the lockfile drift apart without a deliberate update.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] A frozen lockfile (exact pinned versions, including transitives) exists and installs cleanly on a fresh venv
- [ ] CI fails if someone edits `requirements.txt` without regenerating the lockfile
- [ ] A short doc note explains how to regenerate the lockfile when a dependency genuinely needs bumping
