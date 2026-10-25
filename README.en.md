English | [中文版](README.md)

# claude-code-projects-workflow

**When several AI agents work on one repo in parallel: catch overlapping scopes before dispatch, predict merge conflicts before merging.**

A zero-dependency, single-file Python tool, `worktree_tasks.py`, plus three templates. Works with Claude Code,
Codex, or any agent that can work inside a `git worktree` — and with plain human task splits.

## The problem

When you split work across parallel agents, the usual failure is not bad code. It is:

- two tasks whose scopes actually overlap, discovered only when merging
- an agent "helpfully" editing files outside its scope (README, config, shared types)
- a forgotten commit, deleted together with its worktree at cleanup

`worktree_tasks.py` runs one mechanical check at each gate:

```text
plan.json ──lint──> up ──(agents work in their worktrees)──> check ──(you merge)──> down
            │        │                                         │                      │
     overlapping?  create worktree + branch       out of scope? uncommitted?   keeps dirty worktrees
     id/goal/verify  write task brief             conflicts in plan order?     keeps unmerged branches
```

## Quick start

Requires Python 3.10+ and git 2.38+ (`git merge-tree --write-tree`). Nothing to install.

```bash
cp templates/plan.example.json plan.json          # or let an agent write it with templates/coordinator-prompt.md
python worktree_tasks.py --repo <repo> lint plan.json
python worktree_tasks.py --repo <repo> up plan.json   # each worktree gets a .parallel-task.md brief
# start one agent per worktree; ask it to read .parallel-task.md first
python worktree_tasks.py --repo <repo> check plan.json
python worktree_tasks.py --repo <repo> down plan.json --delete-merged
```

Real output (scratch repo, the `api` task deliberately edited an out-of-scope `README.md`):

```text
$ python worktree_tasks.py check plan.json
ERROR: api: README.md is outside the task's paths
ERROR: ui: merging task/ui after the earlier tasks conflicts in: README.md
FAILED: 2 error(s), 0 warning(s)
```

Exit codes: `0` pass, `1` findings, `2` usage or environment error — usable as a script or CI gate.

`lint` and `check` accept `--json` to emit structured findings for an orchestrator or CI to parse (exit code unchanged):

```bash
python worktree_tasks.py lint plan.json --json
```

```json
{"command": "lint", "ok": false, "errors": 1, "warnings": 0,
 "findings": [{"level": "error", "message": "src/api/server.py is claimed by tasks api, refactor"}],
 "message": null}
```

## Plan format

| Field | Meaning |
|---|---|
| `base` | Branch to start from and merge back into. Default `main` |
| `branch_prefix` | Task branch prefix. Default `task/` |
| `worktree_root` | Where worktrees go. Empty = sibling `<repo>.worktrees/`; relative paths resolve against the repo |
| `context_file` | Shared context file the briefs point to |
| `tasks[].id` | Lowercase letters, digits, `-`; used as branch and folder name |
| `tasks[].paths` | Paths the task may change. `*` stays in one segment, `**` spans any depth, trailing `/` means a whole directory |
| `tasks[].verify` | Verification command written into the brief; missing = warning |

## What each command checks

| Command | ERROR (exit 1) | WARNING |
|---|---|---|
| `lint` | an **existing** file claimed by two tasks; bad or duplicate id; missing goal; path outside the repo; missing base | two tasks **may** create the same new file (compares the directory before the first wildcard); no verify command; context file missing |
| `check` | branch changed files outside its paths; uncommitted changes in a worktree; merging back in plan order conflicts | branch missing or has no commits |
| `down` | worktree has uncommitted changes (kept) | branch not merged into base (kept) |

`check` predicts merges with `git merge-tree` chained through temporary commits. It moves no ref and touches no working tree.

## Limits

- Checks are **path-level**. Two tasks touching different files that depend on each other semantically merge cleanly
  and can still break together — run the full test suite after merging.
- `lint`'s "may overlap" is conservative and can be a false positive; it warns and does not block `up`.
- It does not launch agents, call any model API, or merge for you.
- It covers parallel work in **local worktrees**. Claude Code Projects cloud threads run on their own cloud branches, outside your local worktrees, so this tool cannot see them; put their scope boundaries in the project instructions and let the PR flow catch conflicts.

## Related

- [agent-cortex](https://github.com/SanHsien/agent-cortex): a full multi-agent control plane, including an after-the-fact
  `allowed_paths` check. This tool is the lightweight counterpart: one file, no service, plus pre-dispatch overlap
  detection and pre-merge conflict prediction.
- [agent-advisor](https://github.com/SanHsien/agent-advisor): decides **whether** and to which model to delegate. This tool handles file scope after that.
- Claude Code's built-in worktree isolation creates isolated environments; this tool checks whether they step on each other.

Background reading: [`docs/background-notes.md`](docs/background-notes.md) (Chinese reading notes on Claude Code Projects).

## Development

```bash
python -m unittest discover -s tests -v
```

## Multi-agent pipeline

This repo is part of the [agent-relay](https://github.com/SanHsien/agent-relay) multi-agent dispatch and verification pipeline (role: pre-dispatch scope check and conflict prediction for worktrees). Integration with agent-relay is planned (Phase 2). The protocol spec and the index of all related repos live in agent-relay.

## License

[MIT](LICENSE)
