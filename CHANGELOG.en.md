English | [中文版](CHANGELOG.md)

# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), newest first.

## 2026-10-25

### Fixed

- `docs/background-notes.md`: checked item by item against the official Claude Code Projects and worktrees docs. Corrected that the coordinator only sees what threads report back, that shared memory is project instructions plus project memory (not a repo `MEMORY.md`), and that cloud threads read only `CLAUDE.md` and do not load skills, hooks, `.mcp.json` or `settings.json`; added threads that can run locally, auto-fix, beta and plan limits, and `claude --worktree`.
- README "Limits": added that cloud threads do not live in local worktrees, so this tool cannot check them.

### Changed

- `.github/dependabot.yml`: added `fleet-waiver: freshness` — this repo has zero dependencies, so there is no package declaration to compare against.

## 2026-10-24

### Fixed

- `tools/dev_check.ps1`: when `-BaseRef` points to a commit that no longer exists (e.g. after a force push), every gate passed but the script exited 1; it now ends with an explicit `exit 0`.

### Changed

- CI actions bumped to `checkout` v7 / `setup-python` v7, pinned to commit SHAs, with `persist-credentials` off.
- Added `.github/dependabot.yml` (GitHub Actions, weekly) and CodeQL scanning (Python, Actions).

## 2026-10-19

### Added

- `lint` and `check` gain `--json`: emit structured findings (`command` / `ok` / `errors` / `warnings` / `findings` / `message`) for an orchestrator or CI to parse; exit code unchanged.

## 2026-10-16

### Added

- `worktree_tasks.py` with `lint` / `up` / `check` / `down`: pre-dispatch scope overlap check, worktree and task brief creation, pre-merge out-of-scope / uncommitted checks with merge-conflict prediction in plan order, and cleanup that keeps dirty worktrees and unmerged branches.
- Templates: `templates/plan.example.json`, `templates/PROJECT_CONTEXT.md`, `templates/coordinator-prompt.md`.
- Tests (stdlib `unittest`, 24 cases), `tools/dev_check.ps1`, GitHub Actions (Windows + Ubuntu Python 3.10 / 3.13).
- Bilingual README, MIT license, `.gitattributes`, `.editorconfig`.

### Fixed

- `down --delete-merged`: merged branches were refused by `git branch -d` when HEAD was not on base, aborting cleanup; now deleted based on the already verified `--is-ancestor` check.
- `down`: a worktree folder deleted by hand no longer aborts cleanup; `git worktree prune` removes the record.
- Branches are always addressed as `refs/heads/…`: a tag with the same name could make an unmerged branch look merged and get it deleted.
- `down` runs `git worktree prune` first, so `--delete-merged` also works when a worktree folder was deleted by hand.
- A locked worktree whose folder is missing: `down` warns and skips it instead of aborting cleanup of the other tasks.
- A non-UTF-8 plan file reports an error (exit 2) instead of a traceback.

### Changed

- The original Claude Code Projects architecture notes moved to `docs/background-notes.md`, labelled as reading notes.
