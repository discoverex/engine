# Git Conventions

## Branch Naming
- Format: `prefix/short-description`
- Allowed prefixes: `chore`, `docs`, `feat`, `fix`, `ops`, `ref`, `test`

Examples:
- `feat/tiny-pipeline-smoke`
- `docs/context-hygiene`
- `ops/dev-env-docs`

## Branch Initialization Rule
- Every new branch must start with an empty commit.
- Commit message format:
  - `chore: introduce <branch-name> branch`

Examples:
- `chore: introduce dev branch`
- `chore: introduce feat/base-foundation-commits branch`

## Commit Message Prefixes
Use one of the following prefixes only:
- `chore:` maintenance/setup/meta changes
- `docs:` documentation changes
- `feat:` new features
- `fix:` bug fixes
- `ops:` runtime/devcontainer/CI/operational changes
- `ref:` refactoring without behavior change
- `test:` tests and validation coverage

## Commit Scoping Rules
- Keep one concern per commit.
- Avoid mixed commits (code + docs + infra in one commit).
- Use path-targeted staging (`git add <paths>`) instead of `git add .`.

## Merge Rules
- Merge feature branches into `dev` first.
- Use non-fast-forward merges to preserve context:
  - `git merge --no-ff <branch> -m "chore: merge <branch> into dev"`

## Current Practical Workflow
1. Create branch from `dev`.
2. Add empty intro commit.
3. Commit by category (`feat`/`ops`/`docs`/`test`).
4. Validate (`just lint`, `just typecheck`, `just test`).
5. Merge into `dev` with `--no-ff`.
