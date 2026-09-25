# Branching and merge workflow

## Branch roles

- **`main`** — protected. Requires a PR, 1 approving review, and passing status checks. No direct pushes, no force pushes, no deletion. **Only accepts merges whose source branch is `dev`** (see gate below).
- **`dev`** — integration branch. All feature/fix/chore branches merge here first via PR.
- **Everything else** (`feat/...`, `fix/...`, `chore/...`, `docs/...`) — short-lived work branches, cut from `dev`, merged back into `dev` via PR.

## Flow

```
feat/my-thing ──PR──> dev ──PR──> main
fix/my-bug    ──PR──>
```

1. Branch off `dev` (not `main`):
   ```
   git checkout dev && git pull origin dev
   git checkout -b feat/my-thing
   ```
2. Open a PR with `--base dev`.
3. Once merged into `dev`, periodically open a `dev` → `main` PR to ship accumulated work to production.

## The dev-source gate

`main`'s branch protection requires a status check called `require-dev-source` (`.github/workflows/main-source-gate.yml`). That workflow runs on every PR targeting `main` and fails immediately unless the PR's head branch is exactly `dev`:

```yaml
if [ "${{ github.head_ref }}" != "dev" ]; then
  exit 1
fi
```

A PR opened directly from a feature branch into `main` will show this check as failing (or missing, which also blocks merge) — it is not mergeable no matter what else passes. This is enforced technically, not just by convention.

## CI

`.github/workflows/ci.yml` runs the full test suite (`pytest tests/ -q`) on every PR into `main`. Both required checks (`test` and `require-dev-source`) must pass, plus 1 approving review, before a `dev` → `main` PR can merge.

`dev` itself currently has no branch protection — feature-branch PRs into `dev` can merge as soon as their own CI passes, no separate review gate.
