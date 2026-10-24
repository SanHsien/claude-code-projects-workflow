English | [中文版](CHANGELOG.md)

# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), newest first.

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
