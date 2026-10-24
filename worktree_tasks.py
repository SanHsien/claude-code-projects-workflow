#!/usr/bin/env python3
"""worktree_tasks: 平行 AI 任務的 git worktree 派工前檢查、建立、合併前檢查與收尾。

只用 Python 標準函式庫與 git（>= 2.38，需要 `git merge-tree --write-tree`）。

子指令：
  lint  檢查計畫檔：格式、任務 id、各任務檔案範圍是否重疊
  up    依計畫為每個任務建立 worktree 與分支，並寫入任務說明檔
  check 每個分支是否只改了自己範圍內的檔案、依序合併回 base 會不會衝突
  down  移除 worktree；加 --delete-merged 時只刪已合併進 base 的分支

結束碼：0 = 通過，1 = 檢查發現問題，2 = 用法或環境錯誤。
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

BRIEF_NAME = ".parallel-task.md"
TASK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
WILDCARDS = set("*?[")


class UsageError(Exception):
    """計畫檔或環境有問題，無法繼續（結束碼 2）。"""


@dataclass
class Task:
    id: str
    goal: str
    paths: list[str]
    verify: str = ""


@dataclass
class Plan:
    base: str
    branch_prefix: str
    worktree_root: str
    context_file: str
    tasks: list[Task] = field(default_factory=list)

    def branch(self, task: Task) -> str:
        return f"{self.branch_prefix}{task.id}"


@dataclass
class Finding:
    level: str  # "error" | "warning"
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper()}: {self.message}"


# ---------------------------------------------------------------- 路徑比對

def normalize(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def match_path(path: str, pattern: str) -> bool:
    """以 / 分段比對。`**` 可吃零到多段；結尾是 / 的 pattern 代表整個目錄。"""
    path = normalize(path)
    if pattern.endswith("/"):
        pattern = pattern.rstrip("/") + "/**"
    return _match_parts(path.split("/"), normalize(pattern).split("/"))


def _match_parts(parts: list[str], pats: list[str]) -> bool:
    if not pats:
        return not parts
    head, rest = pats[0], pats[1:]
    if head == "**":
        return any(_match_parts(parts[i:], rest) for i in range(len(parts) + 1))
    if not parts:
        return False
    return fnmatch.fnmatchcase(parts[0], head) and _match_parts(parts[1:], rest)


def literal_prefix(pattern: str) -> str:
    """pattern 在第一個萬用字元之前、完整的目錄段。`src/api/*.py` -> `src/api`。"""
    if pattern.endswith("/"):
        pattern = pattern.rstrip("/") + "/**"
    out = []
    for part in normalize(pattern).split("/"):
        if WILDCARDS & set(part):
            break
        out.append(part)
    else:
        return "/".join(out)  # 沒有萬用字元：整條就是一個檔案
    return "/".join(out)


def may_overlap(a: str, b: str) -> bool:
    """保守估計兩個 pattern 能不能匹配到同一個（可能還不存在的）檔案。"""
    pa, pb = literal_prefix(a), literal_prefix(b)
    if not pa or not pb:
        return True  # 其中一個從根目錄就是萬用字元
    return pa == pb or pa.startswith(pb + "/") or pb.startswith(pa + "/") or \
        match_path(pa, b) or match_path(pb, a)


# ---------------------------------------------------------------- git

def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and proc.returncode != 0:
        raise UsageError(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def repo_root(start: Path) -> Path:
    proc = git(start, "rev-parse", "--show-toplevel", check=False)
    if proc.returncode != 0:
        raise UsageError(f"{start} is not inside a git repository")
    return Path(proc.stdout.strip())


def ref_exists(repo: Path, ref: str) -> bool:
    return git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False).returncode == 0


def tracked_files(repo: Path, ref: str) -> list[str]:
    return [f for f in git(repo, "ls-tree", "-r", "--name-only", ref).stdout.splitlines() if f]


def worktree_list(repo: Path) -> dict[str, str]:
    """worktree 路徑（正規化）-> 分支名稱（沒有分支則為空字串）。"""
    out, current = {}, None
    for line in git(repo, "worktree", "list", "--porcelain").stdout.splitlines():
        if line.startswith("worktree "):
            current = _norm_fs(line[len("worktree "):])
            out[current] = ""
        elif line.startswith("branch ") and current is not None:
            out[current] = line[len("branch "):].removeprefix("refs/heads/")
    return out


def _norm_fs(p: str | Path) -> str:
    return str(Path(p).resolve()).replace("\\", "/").lower() if sys.platform == "win32" \
        else str(Path(p).resolve())


# ---------------------------------------------------------------- 計畫檔

def load_plan(path: Path) -> Plan:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise UsageError(f"plan file not found: {path}") from None
    except UnicodeDecodeError:
        raise UsageError(f"plan file is not UTF-8: {path}") from None
    except json.JSONDecodeError as exc:
        raise UsageError(f"plan file is not valid JSON: {exc}") from None
    if not isinstance(raw, dict) or not isinstance(raw.get("tasks"), list) or not raw["tasks"]:
        raise UsageError("plan must be an object with a non-empty 'tasks' list")
    tasks = []
    for i, t in enumerate(raw["tasks"]):
        if not isinstance(t, dict):
            raise UsageError(f"tasks[{i}] must be an object")
        paths = t.get("paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p.strip() for p in paths):
            raise UsageError(f"tasks[{i}].paths must be a non-empty list of strings")
        tasks.append(Task(
            id=str(t.get("id", "")),
            goal=str(t.get("goal", "")).strip(),
            paths=[p.strip() for p in paths],
            verify=str(t.get("verify", "")).strip(),
        ))
    return Plan(
        base=str(raw.get("base", "main")),
        branch_prefix=str(raw.get("branch_prefix", "task/")),
        worktree_root=str(raw.get("worktree_root", "")),
        context_file=str(raw.get("context_file", "")),
        tasks=tasks,
    )


def worktree_root(plan: Plan, repo: Path) -> Path:
    if plan.worktree_root:
        root = Path(plan.worktree_root)
        return root if root.is_absolute() else (repo / root).resolve()
    return repo.parent / f"{repo.name}.worktrees"


# ---------------------------------------------------------------- lint

def lint(plan: Plan, repo: Path) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()
    for t in plan.tasks:
        if not TASK_ID_RE.match(t.id):
            findings.append(Finding("error", f"task id {t.id!r} must match {TASK_ID_RE.pattern}"))
        if t.id in seen:
            findings.append(Finding("error", f"duplicate task id {t.id!r}"))
        seen.add(t.id)
        if not t.goal:
            findings.append(Finding("error", f"task {t.id!r} has no goal"))
        if not t.verify:
            findings.append(Finding("warning", f"task {t.id!r} has no verify command"))
        for p in t.paths:
            if normalize(p).startswith("..") or Path(p).is_absolute():
                findings.append(Finding("error", f"task {t.id!r} path {p!r} points outside the repository"))

    if not ref_exists(repo, plan.base):
        findings.append(Finding("error", f"base ref {plan.base!r} does not exist"))
        return findings
    if plan.context_file and not (repo / plan.context_file).is_file():
        findings.append(Finding("warning", f"context_file {plan.context_file!r} does not exist yet"))

    files = tracked_files(repo, plan.base)
    owners: dict[str, list[str]] = {}
    for t in plan.tasks:
        hits = [f for f in files if any(match_path(f, p) for p in t.paths)]
        for f in hits:
            owners.setdefault(f, []).append(t.id)
    for f, ids in sorted(owners.items()):
        if len(ids) > 1:
            findings.append(Finding("error", f"{f} is claimed by tasks {', '.join(ids)}"))

    reported = {tuple(sorted(ids)) for ids in owners.values() if len(ids) > 1}
    for i, a in enumerate(plan.tasks):
        for b in plan.tasks[i + 1:]:
            if tuple(sorted((a.id, b.id))) in reported:
                continue
            pairs = [(pa, pb) for pa in a.paths for pb in b.paths if may_overlap(pa, pb)]
            if pairs:
                pa, pb = pairs[0]
                findings.append(Finding(
                    "warning",
                    f"tasks {a.id} and {b.id} may create the same new files ({pa!r} vs {pb!r})",
                ))
    return findings


# ---------------------------------------------------------------- up

def brief_text(plan: Plan, task: Task, repo: Path) -> str:
    others = [f"- `{p}`（{o.id}）" for o in plan.tasks if o is not task for p in o.paths]
    lines = [
        f"# 平行任務：{task.id}",
        "",
        "> 本檔由 worktree_tasks.py 產生，已列入 git 排除清單，不要提交。",
        "",
        "## 目標",
        "",
        task.goal,
        "",
        "## 只能修改這些路徑",
        "",
        *[f"- `{p}`" for p in task.paths],
        "",
        "## 不要碰（其他平行任務負責）",
        "",
        *(others or ["- （無）"]),
        "",
        "## 完成條件",
        "",
        f"- 在本分支 `{plan.branch(task)}` 提交所有改動，工作區保持乾淨",
        f"- 驗證指令通過：`{task.verify}`" if task.verify else "- 計畫沒有指定驗證指令，請回報你怎麼驗證",
        "- 需要改範圍外的檔案時停下來回報，不要自己改",
    ]
    if plan.context_file:
        lines += ["", "## 共享專案脈絡", "", f"開工前先讀：`{(repo / plan.context_file).as_posix()}`"]
    return "\n".join(lines) + "\n"


def ensure_excluded(repo: Path) -> None:
    common = Path(git(repo, "rev-parse", "--git-common-dir").stdout.strip())
    if not common.is_absolute():
        common = (repo / common).resolve()
    exclude = common / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    entry = f"/{BRIEF_NAME}"
    if entry not in existing.splitlines():
        sep = "" if existing.endswith("\n") or not existing else "\n"
        exclude.write_text(existing + sep + entry + "\n", encoding="utf-8")


def up(plan: Plan, repo: Path) -> list[str]:
    root = worktree_root(plan, repo)
    existing = worktree_list(repo)
    ensure_excluded(repo)
    log = []
    for t in plan.tasks:
        path, branch = root / t.id, plan.branch(t)
        key = _norm_fs(path)
        if key in existing:
            if existing[key] != branch:
                raise UsageError(f"{path} is already a worktree on branch {existing[key]!r}, expected {branch!r}")
            log.append(f"exists  {t.id}: {path}")
        else:
            if path.exists() and any(path.iterdir()):
                raise UsageError(f"{path} exists and is not empty")
            if ref_exists(repo, f"refs/heads/{branch}"):
                git(repo, "worktree", "add", str(path), branch)
            else:
                git(repo, "worktree", "add", "-b", branch, str(path), plan.base)
            log.append(f"created {t.id}: {path} ({branch})")
        (path / BRIEF_NAME).write_text(brief_text(plan, t, repo), encoding="utf-8")
    return log


# ---------------------------------------------------------------- check

def changed_files(repo: Path, base: str, branch: str) -> list[str]:
    out = git(repo, "diff", "--name-only", "--no-renames", f"{base}...refs/heads/{branch}").stdout
    return [f for f in out.splitlines() if f]


def dirty_files(worktree: Path) -> list[str]:
    out = git(worktree, "status", "--porcelain", "--untracked-files=all").stdout
    files = []
    for line in out.splitlines():
        name = line[3:].split(" -> ")[-1].strip('"')
        if name != BRIEF_NAME:
            files.append(name)
    return files


def check(plan: Plan, repo: Path) -> list[Finding]:
    findings: list[Finding] = []
    if not ref_exists(repo, plan.base):
        return [Finding("error", f"base ref {plan.base!r} does not exist")]
    root = worktree_root(plan, repo)
    present = []
    for t in plan.tasks:
        branch = plan.branch(t)
        if not ref_exists(repo, f"refs/heads/{branch}"):
            findings.append(Finding("warning", f"{t.id}: branch {branch} does not exist (not started?)"))
            continue
        present.append(t)
        changed = changed_files(repo, plan.base, branch)
        if not changed:
            findings.append(Finding("warning", f"{t.id}: no committed changes yet"))
        for f in changed:
            if not any(match_path(f, p) for p in t.paths):
                findings.append(Finding("error", f"{t.id}: {f} is outside the task's paths"))
        wt = root / t.id
        if wt.is_dir():
            dirty = dirty_files(wt)
            if dirty:
                findings.append(Finding("error", f"{t.id}: uncommitted changes in worktree: {', '.join(dirty[:5])}"))

    # 依計畫順序模擬把每個分支合併回 base，用暫時 commit 串接，不動任何 ref 或工作區
    current = git(repo, "rev-parse", f"{plan.base}^{{commit}}").stdout.strip()
    for t in present:
        branch = plan.branch(t)
        proc = git(repo, "merge-tree", "--write-tree", "--name-only", "--no-messages",
                   current, f"refs/heads/{branch}", check=False)
        lines = proc.stdout.splitlines()
        if proc.returncode == 1:
            conflicted = [l for l in lines[1:] if l]
            findings.append(Finding(
                "error",
                f"{t.id}: merging {branch} after the earlier tasks conflicts in: {', '.join(conflicted)}",
            ))
            continue
        if proc.returncode != 0:
            raise UsageError(f"git merge-tree failed: {proc.stderr.strip()}")
        current = git(repo, "commit-tree", lines[0], "-p", current, "-p", f"refs/heads/{branch}",
                      "-m", f"worktree_tasks simulated merge of {branch}").stdout.strip()
    return findings


# ---------------------------------------------------------------- down

def down(plan: Plan, repo: Path, delete_merged: bool) -> tuple[list[str], list[Finding]]:
    root = worktree_root(plan, repo)
    log, findings = [], []
    # 資料夾被手動刪掉的 worktree 紀錄仍會佔住分支，讓 `branch -D` 失敗；先 prune 再處理
    stale = [t for t in plan.tasks if _norm_fs(root / t.id) in worktree_list(repo) and not (root / t.id).is_dir()]
    git(repo, "worktree", "prune")
    existing = worktree_list(repo)
    log += [f"pruned {t.id}: folder already gone ({root / t.id})"
            for t in stale if _norm_fs(root / t.id) not in existing]
    for t in plan.tasks:
        path, branch = root / t.id, plan.branch(t)
        if _norm_fs(path) in existing and not path.is_dir():
            # prune 不動被 lock 的紀錄；資料夾不在就沒辦法檢查，分支也還被佔住
            findings.append(Finding("warning", f"{t.id}: worktree folder is missing but its record is kept "
                                               f"(locked?), skipped; see `git worktree unlock`: {path}"))
            continue
        if _norm_fs(path) in existing:
            dirty = dirty_files(path)
            if dirty:
                findings.append(Finding("error", f"{t.id}: worktree has uncommitted changes, kept: {path}"))
                continue
            brief = path / BRIEF_NAME
            if brief.exists():
                brief.unlink()
            git(repo, "worktree", "remove", str(path))
            log.append(f"removed {t.id}: {path}")
        if delete_merged and ref_exists(repo, f"refs/heads/{branch}"):
            merged = git(repo, "merge-base", "--is-ancestor", f"refs/heads/{branch}", plan.base, check=False).returncode == 0
            if merged:
                # 已用 --is-ancestor 確認併入 base；`branch -d` 會改拿目前 HEAD 判斷，HEAD 不在 base 時誤拒
                git(repo, "branch", "-D", branch)
                log.append(f"deleted branch {branch}")
            else:
                findings.append(Finding("warning", f"{t.id}: branch {branch} is not merged into {plan.base}, kept"))
    git(repo, "worktree", "prune")
    return log, findings


# ---------------------------------------------------------------- CLI

def _report(findings: list[Finding], ok_message: str, as_json: bool = False, command: str = "") -> int:
    errors = sum(f.level == "error" for f in findings)
    if as_json:
        print(json.dumps({
            "command": command,
            "ok": errors == 0,
            "errors": errors,
            "warnings": len(findings) - errors,
            "findings": [{"level": f.level, "message": f.message} for f in findings],
            "message": None if errors else ok_message,
        }, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    for f in findings:
        print(f)
    if errors:
        print(f"FAILED: {errors} error(s), {len(findings) - errors} warning(s)")
        return 1
    print(f"OK: {ok_message}" + (f" ({len(findings)} warning(s))" if findings else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="worktree_tasks", description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="git repository (default: current directory)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("lint", "up", "check", "down"):
        p = sub.add_parser(name)
        p.add_argument("plan", help="plan JSON file")
        if name in ("lint", "check"):
            p.add_argument("--json", action="store_true", help="emit findings as JSON (exit code unchanged)")
        if name == "down":
            p.add_argument("--delete-merged", action="store_true",
                           help="also delete task branches already merged into base")
    args = parser.parse_args(argv)

    try:
        repo = repo_root(Path(args.repo))
        plan = load_plan(Path(args.plan))
        if args.command == "lint":
            return _report(lint(plan, repo), f"{len(plan.tasks)} task(s), no overlapping paths",
                           args.json, "lint")
        if args.command == "up":
            findings = lint(plan, repo)
            if any(f.level == "error" for f in findings):
                return _report(findings, "")
            for f in findings:
                print(f)
            for line in up(plan, repo):
                print(line)
            print(f"OK: briefs written as {BRIEF_NAME} in each worktree")
            return 0
        if args.command == "check":
            return _report(check(plan, repo), "every branch stays in scope and merges cleanly in plan order",
                           args.json, "check")
        log, findings = down(plan, repo, args.delete_merged)
        for line in log:
            print(line)
        return _report(findings, "cleanup done")
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
