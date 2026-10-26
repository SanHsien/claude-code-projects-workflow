"""worktree_tasks.py 的測試。每個測試建立自己的暫存 git repo，需要 PATH 上有 git >= 2.38。"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import worktree_tasks as wt  # noqa: E402


def run(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout


class MatchPathTests(unittest.TestCase):
    def test_double_star_matches_zero_or_more_dirs(self):
        self.assertTrue(wt.match_path("src/api/x.py", "src/**"))
        self.assertTrue(wt.match_path("src/x.py", "src/**/*.py"))
        self.assertTrue(wt.match_path("src/a/b/x.py", "src/**/*.py"))
        self.assertFalse(wt.match_path("lib/x.py", "src/**"))

    def test_single_star_stays_in_one_segment(self):
        self.assertTrue(wt.match_path("src/x.py", "src/*.py"))
        self.assertFalse(wt.match_path("src/a/x.py", "src/*.py"))

    def test_trailing_slash_means_directory(self):
        self.assertTrue(wt.match_path("docs/a/b.md", "docs/"))
        self.assertFalse(wt.match_path("docs.md", "docs/"))

    def test_backslashes_are_normalized(self):
        self.assertTrue(wt.match_path("src\\api\\x.py", "src/api/*.py"))

    def test_may_overlap(self):
        self.assertTrue(wt.may_overlap("src/api/**", "src/**/*.py"))
        self.assertTrue(wt.may_overlap("**/*.md", "docs/"))
        self.assertFalse(wt.may_overlap("src/api/**", "src/ui/**"))
        self.assertFalse(wt.may_overlap("src/a.py", "src/b.py"))
        self.assertTrue(wt.may_overlap("src/a.py", "src/*.py"))


class TemplateTests(unittest.TestCase):
    def test_example_plan_is_valid(self):
        plan = wt.load_plan(ROOT / "templates" / "plan.example.json")
        self.assertEqual(len(plan.tasks), 3)
        for t in plan.tasks:
            self.assertRegex(t.id, wt.TASK_ID_RE)
            self.assertTrue(t.goal and t.verify)
        for i, a in enumerate(plan.tasks):
            for b in plan.tasks[i + 1:]:
                for pa in a.paths:
                    for pb in b.paths:
                        self.assertFalse(wt.may_overlap(pa, pb), (pa, pb))


class RepoTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wt-test-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        run(self.repo, "init", "-q", "-b", "main")
        run(self.repo, "config", "user.email", "test@example.com")
        run(self.repo, "config", "user.name", "Test")
        run(self.repo, "config", "core.autocrlf", "false")
        self.write("src/api/server.py", "print('api')\n")
        self.write("src/ui/app.js", "console.log('ui')\n")
        self.write("README.md", "# demo\n")
        self.write("PROJECT_CONTEXT.md", "# context\n")
        self.commit("init")

    def tearDown(self):
        subprocess.run(["git", "-C", str(self.repo), "worktree", "prune"], capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel: str, text: str, where: Path | None = None) -> None:
        p = (where or self.repo) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def commit(self, msg: str, where: Path | None = None) -> None:
        run(where or self.repo, "add", "-A")
        run(where or self.repo, "commit", "-q", "-m", msg)

    def plan(self, tasks: list[dict], **extra) -> Path:
        data = {"base": "main", "context_file": "PROJECT_CONTEXT.md",
                "worktree_root": str(self.tmp / "wts"), "tasks": tasks, **extra}
        path = self.tmp / "plan.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def cli(self, *args: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = wt.main(["--repo", str(self.repo), *args])
        return code, out.getvalue() + err.getvalue()

    TWO_TASKS = [
        {"id": "api", "goal": "add endpoint", "paths": ["src/api/**"], "verify": "python -m unittest"},
        {"id": "ui", "goal": "add button", "paths": ["src/ui/**"], "verify": "npm test"},
    ]


class LintTests(RepoTestCase):
    def test_clean_plan_passes(self):
        code, out = self.cli("lint", str(self.plan(self.TWO_TASKS)))
        self.assertEqual(code, 0, out)
        self.assertIn("OK: 2 task(s)", out)

    def test_existing_file_claimed_twice_is_error(self):
        tasks = [self.TWO_TASKS[0], {"id": "refactor", "goal": "g", "paths": ["src/**"], "verify": "x"}]
        code, out = self.cli("lint", str(self.plan(tasks)))
        self.assertEqual(code, 1)
        self.assertIn("src/api/server.py is claimed by tasks api, refactor", out)

    def test_possible_new_file_overlap_is_warning(self):
        tasks = [{"id": "a", "goal": "g", "paths": ["docs/**"], "verify": "x"},
                 {"id": "b", "goal": "g", "paths": ["docs/guide/*.md"], "verify": "x"}]
        code, out = self.cli("lint", str(self.plan(tasks)))
        self.assertEqual(code, 0, out)
        self.assertIn("WARNING: tasks a and b may create the same new files", out)

    def test_bad_ids_and_paths_are_errors(self):
        tasks = [{"id": "Bad ID", "goal": "g", "paths": ["../outside"], "verify": "x"},
                 {"id": "dup", "goal": "", "paths": ["a/**"]},
                 {"id": "dup", "goal": "g", "paths": ["b/**"], "verify": "x"}]
        code, out = self.cli("lint", str(self.plan(tasks)))
        self.assertEqual(code, 1)
        self.assertIn("task id 'Bad ID'", out)
        self.assertIn("points outside the repository", out)
        self.assertIn("duplicate task id 'dup'", out)
        self.assertIn("has no goal", out)
        self.assertIn("WARNING: task 'dup' has no verify command", out)

    def test_json_output(self):
        import json as _json
        code, out = self.cli("lint", str(self.plan(self.TWO_TASKS)), "--json")
        self.assertEqual(code, 0, out)
        data = _json.loads(out)
        self.assertEqual((data["command"], data["ok"], data["errors"], data["findings"]), ("lint", True, 0, []))
        tasks = [self.TWO_TASKS[0], {"id": "refactor", "goal": "g", "paths": ["src/**"], "verify": "x"}]
        code, out = self.cli("lint", str(self.plan(tasks)), "--json")
        self.assertEqual(code, 1)
        data = _json.loads(out)
        self.assertFalse(data["ok"])
        self.assertGreaterEqual(data["errors"], 1)
        self.assertTrue(any(f["level"] == "error" for f in data["findings"]))

    def test_missing_base_is_error(self):
        code, out = self.cli("lint", str(self.plan(self.TWO_TASKS, base="nope")))
        self.assertEqual(code, 1)
        self.assertIn("base ref 'nope' does not exist", out)

    def test_invalid_plan_is_usage_error(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{\"tasks\": []}", encoding="utf-8")
        code, out = self.cli("lint", str(bad))
        self.assertEqual(code, 2)
        self.assertIn("non-empty 'tasks' list", out)
        bad.write_bytes('{"tasks": [{"goal": "中文"}]}'.encode("cp950"))
        code, out = self.cli("lint", str(bad))
        self.assertEqual(code, 2)
        self.assertIn("not UTF-8", out)


class LifecycleTests(RepoTestCase):
    def test_up_creates_worktrees_and_briefs_idempotently(self):
        plan = self.plan(self.TWO_TASKS)
        code, out = self.cli("up", str(plan))
        self.assertEqual(code, 0, out)
        brief = (self.tmp / "wts" / "api" / wt.BRIEF_NAME).read_text(encoding="utf-8")
        self.assertIn("add endpoint", brief)
        self.assertIn("`src/ui/**`（ui）", brief)
        self.assertIn("PROJECT_CONTEXT.md", brief)
        self.assertIn("task/api", run(self.repo, "branch", "--list"))
        # brief 被排除，不會出現在 git status
        self.assertEqual(run(self.tmp / "wts" / "api", "status", "--porcelain"), "")
        code, out = self.cli("up", str(plan))
        self.assertEqual(code, 0, out)
        self.assertIn("exists  api", out)

    def test_up_refuses_overlapping_plan(self):
        tasks = [self.TWO_TASKS[0], {"id": "all", "goal": "g", "paths": ["src/**"], "verify": "x"}]
        code, _ = self.cli("up", str(self.plan(tasks)))
        self.assertEqual(code, 1)
        self.assertFalse((self.tmp / "wts").exists())

    def test_check_passes_for_scoped_disjoint_work(self):
        plan = self.plan(self.TWO_TASKS)
        self.cli("up", str(plan))
        api, ui = self.tmp / "wts" / "api", self.tmp / "wts" / "ui"
        self.write("src/api/routes.py", "x = 1\n", api)
        self.commit("api", api)
        self.write("src/ui/button.js", "b()\n", ui)
        self.commit("ui", ui)
        code, out = self.cli("check", str(plan))
        self.assertEqual(code, 0, out)
        self.assertIn("merges cleanly", out)

    def test_check_json_output(self):
        import json as _json
        plan = self.plan(self.TWO_TASKS)
        self.cli("up", str(plan))
        api, ui = self.tmp / "wts" / "api", self.tmp / "wts" / "ui"
        self.write("src/api/routes.py", "x = 1\n", api)
        self.commit("api", api)
        self.write("src/ui/button.js", "b()\n", ui)
        self.commit("ui", ui)
        code, out = self.cli("check", str(plan), "--json")
        self.assertEqual(code, 0, out)
        data = _json.loads(out)
        self.assertEqual((data["command"], data["ok"]), ("check", True))

    def test_check_flags_out_of_scope_and_dirty(self):
        plan = self.plan(self.TWO_TASKS)
        self.cli("up", str(plan))
        api = self.tmp / "wts" / "api"
        self.write("README.md", "# changed\n", api)
        self.commit("touch readme", api)
        self.write("src/api/wip.py", "pass\n", api)
        code, out = self.cli("check", str(plan))
        self.assertEqual(code, 1)
        self.assertIn("api: README.md is outside the task's paths", out)
        self.assertIn("api: uncommitted changes in worktree: src/api/wip.py", out)
        self.assertIn("ui: no committed changes yet", out)

    def test_check_predicts_merge_conflict_in_plan_order(self):
        # 兩個任務都宣告了同一個（尚不存在的）目錄，lint 只會給警告；check 抓出真的衝突
        tasks = [{"id": "a", "goal": "g", "paths": ["shared/**"], "verify": "x"},
                 {"id": "b", "goal": "g", "paths": ["shared/*.txt"], "verify": "x"}]
        plan = self.plan(tasks)
        code, out = self.cli("up", str(plan))
        self.assertEqual(code, 0, out)
        for name, text in (("a", "from a\n"), ("b", "from b\n")):
            w = self.tmp / "wts" / name
            self.write("shared/notes.txt", text, w)
            self.commit(name, w)
        before = run(self.repo, "rev-parse", "main")
        code, out = self.cli("check", str(plan))
        self.assertEqual(code, 1)
        self.assertIn("b: merging task/b after the earlier tasks conflicts in: shared/notes.txt", out)
        self.assertEqual(run(self.repo, "rev-parse", "main"), before)  # 模擬不動 ref

    def test_down_keeps_dirty_and_unmerged(self):
        plan = self.plan(self.TWO_TASKS)
        self.cli("up", str(plan))
        api, ui = self.tmp / "wts" / "api", self.tmp / "wts" / "ui"
        self.write("src/api/routes.py", "x = 1\n", api)
        self.commit("api", api)
        self.write("src/ui/wip.js", "w\n", ui)  # 沒提交
        run(self.repo, "merge", "-q", "--no-edit", "task/api")
        code, out = self.cli("down", str(plan), "--delete-merged")
        self.assertEqual(code, 1)
        self.assertIn("removed api", out)
        self.assertIn("deleted branch task/api", out)
        self.assertIn("ui: worktree has uncommitted changes, kept", out)
        self.assertTrue(ui.is_dir())
        self.assertFalse(api.exists())
        self.assertIn("task/ui", run(self.repo, "branch", "--list"))

    def test_down_deletes_merged_branch_when_head_is_elsewhere(self):
        plan = self.plan(self.TWO_TASKS)
        self.cli("up", str(plan))
        api = self.tmp / "wts" / "api"
        self.write("src/api/routes.py", "x = 1\n", api)
        self.commit("api", api)
        run(self.repo, "merge", "-q", "--no-edit", "task/api")
        run(self.repo, "checkout", "-q", "-b", "other", "HEAD~1")  # HEAD 不含 task/api
        code, out = self.cli("down", str(plan), "--delete-merged")
        self.assertEqual(code, 0, out)
        self.assertIn("deleted branch task/api", out)
        self.assertIn("removed ui", out)

    def test_down_handles_manually_deleted_folder(self):
        plan = self.plan(self.TWO_TASKS)
        self.cli("up", str(plan))
        shutil.rmtree(self.tmp / "wts" / "ui")
        code, out = self.cli("down", str(plan))
        self.assertEqual(code, 0, out)
        self.assertIn("pruned ui: folder already gone", out)
        self.assertIn("removed api", out)
        self.assertNotIn("wts/ui", run(self.repo, "worktree", "list").replace("\\", "/"))

    def test_down_deleted_folder_with_merged_branch(self):
        plan = self.plan(self.TWO_TASKS)
        self.cli("up", str(plan))
        api = self.tmp / "wts" / "api"
        self.write("src/api/routes.py", "x = 1\n", api)
        self.commit("api", api)
        run(self.repo, "merge", "-q", "--no-edit", "task/api")
        shutil.rmtree(api)
        code, out = self.cli("down", str(plan), "--delete-merged")
        self.assertEqual(code, 0, out)
        self.assertIn("pruned api: folder already gone", out)
        self.assertIn("deleted branch task/api", out)

    def test_down_skips_locked_worktree_with_missing_folder(self):
        plan = self.plan(self.TWO_TASKS)
        self.cli("up", str(plan))
        api = self.tmp / "wts" / "api"
        run(self.repo, "worktree", "lock", str(api))
        shutil.rmtree(api)
        code, out = self.cli("down", str(plan), "--delete-merged")
        self.assertEqual(code, 0, out)
        self.assertIn("api: worktree folder is missing but its record is kept (locked?)", out)
        self.assertNotIn("pruned api", out)
        self.assertIn("removed ui", out)
        self.assertIn("task/api", run(self.repo, "branch", "--list"))
        run(self.repo, "worktree", "unlock", str(api))

    def test_same_named_tag_does_not_hide_unmerged_branch(self):
        plan = self.plan(self.TWO_TASKS)
        run(self.repo, "tag", "task/api")  # 指向 main，已「合併」
        self.cli("up", str(plan))
        api = self.tmp / "wts" / "api"
        self.write("src/api/routes.py", "x = 1\n", api)
        self.commit("api", api)  # 分支本身沒合併
        code, out = self.cli("check", str(plan))
        self.assertNotIn("api: no committed changes yet", out)
        code, out = self.cli("down", str(plan), "--delete-merged")
        self.assertIn("api: branch task/api is not merged into main, kept", out)
        self.assertTrue(run(self.repo, "rev-parse", "--verify", "refs/heads/task/api").strip())

    def test_down_never_deletes_unmerged_branch(self):
        plan = self.plan(self.TWO_TASKS)
        self.cli("up", str(plan))
        ui = self.tmp / "wts" / "ui"
        self.write("src/ui/button.js", "b()\n", ui)
        self.commit("ui", ui)
        code, out = self.cli("down", str(plan), "--delete-merged")
        self.assertEqual(code, 0, out)
        self.assertIn("removed ui", out)
        self.assertIn("ui: branch task/ui is not merged into main, kept", out)
        self.assertIn("task/ui", run(self.repo, "branch", "--list"))



class QuotedPathTests(RepoTestCase):
    """git 預設把非 ASCII 檔名輸出成 "\\344\\270..."；比對與回報都得拿到真實檔名。"""

    def test_lint_sees_overlap_on_non_ascii_tracked_file(self):
        self.write("文件/說明.md", "x\n")
        self.commit("add zh doc")
        tasks = [{"id": "a", "goal": "g", "paths": ["文件/**"], "verify": "x"},
                 {"id": "b", "goal": "g", "paths": ["文件/說明.md"], "verify": "x"}]
        code, out = self.cli("lint", str(self.plan(tasks)))
        self.assertEqual(code, 1, out)
        self.assertIn("文件/說明.md is claimed by tasks a, b", out)

    def test_check_accepts_non_ascii_file_inside_scope(self):
        tasks = [{"id": "docs", "goal": "g", "paths": ["文件/**"], "verify": "x"}]
        plan = self.plan(tasks)
        self.cli("up", str(plan))
        d = self.tmp / "wts" / "docs"
        self.write("文件/新增.md", "x\n", d)
        self.commit("zh", d)
        code, out = self.cli("check", str(plan))
        self.assertEqual(code, 0, out)

    def test_check_reports_non_ascii_dirty_file_by_real_name(self):
        tasks = [{"id": "docs", "goal": "g", "paths": ["文件/**"], "verify": "x"}]
        plan = self.plan(tasks)
        self.cli("up", str(plan))
        self.write("文件/草稿.md", "x\n", self.tmp / "wts" / "docs")
        code, out = self.cli("check", str(plan))
        self.assertEqual(code, 1)
        self.assertIn("文件/草稿.md", out)

    def test_check_reports_non_ascii_conflict_by_real_name(self):
        tasks = [{"id": "a", "goal": "g", "paths": ["文件/**"], "verify": "x"},
                 {"id": "b", "goal": "g", "paths": ["文件/*.txt"], "verify": "x"}]
        plan = self.plan(tasks)
        self.cli("up", str(plan))
        for name in ("a", "b"):
            w = self.tmp / "wts" / name
            self.write("文件/筆記.txt", f"from {name}\n", w)
            self.commit(name, w)
        code, out = self.cli("check", str(plan))
        self.assertEqual(code, 1, out)
        self.assertIn("conflicts in: 文件/筆記.txt", out)

    def test_dirty_files_handles_renames(self):
        self.write("舊名.md", "x\n")
        self.commit("add")
        run(self.repo, "mv", "舊名.md", "新名.md")
        self.assertEqual(wt.dirty_files(self.repo), ["新名.md"])


class PlanValidationTests(RepoTestCase):
    def test_task_id_with_trailing_newline_is_rejected(self):
        tasks = [{"id": "api\n", "goal": "g", "paths": ["src/api/**"], "verify": "x"}]
        code, out = self.cli("lint", str(self.plan(tasks)))
        self.assertEqual(code, 1, out)
        self.assertIn("task id", out)

    def test_windows_reserved_device_names_are_rejected(self):
        for bad in ("con", "nul", "aux", "com1", "lpt9", "prn"):
            tasks = [{"id": bad, "goal": "g", "paths": ["src/api/**"], "verify": "x"}]
            code, out = self.cli("lint", str(self.plan(tasks)))
            self.assertEqual(code, 1, (bad, out))
            self.assertIn("reserved", out)

    def test_invalid_branch_prefix_is_an_error_not_a_crash_in_up(self):
        plan = self.plan(self.TWO_TASKS, branch_prefix="bad prefix/")
        code, out = self.cli("lint", str(plan))
        self.assertEqual(code, 1, out)
        self.assertIn("branch", out)
        code, out = self.cli("up", str(plan))
        self.assertEqual(code, 1, out)
        self.assertFalse((self.tmp / "wts").exists())


if __name__ == "__main__":
    unittest.main()
