"""check_links.py 的測試。

驗證 Markdown 相對連結檢查器，包含檔案不存在與大小寫不符（Windows/macOS/Linux）檢查。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import check_links  # noqa: E402


class CheckLinksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        # 建立測試目錄與檔案結構
        (self.dir / "sub").mkdir(parents=True, exist_ok=True)
        (self.dir / "Target.md").write_text("# Target\n", encoding="utf-8")
        (self.dir / "sub" / "Nested.md").write_text("# Nested\n", encoding="utf-8")
        self.doc = self.dir / "doc.md"
        self.doc.write_text("# Doc\n", encoding="utf-8")
        self.sub_doc = self.dir / "sub" / "sub_doc.md"
        self.sub_doc.write_text("# Sub Doc\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_case_resolves(self):
        self.assertIsNone(check_links.missing_target(self.doc, "Target.md"))
        self.assertIsNone(check_links.missing_target(self.doc, "./Target.md"))
        self.assertIsNone(check_links.missing_target(self.doc, "sub/Nested.md"))
        self.assertIsNone(check_links.missing_target(self.doc, "sub/../Target.md"))
        self.assertIsNone(check_links.missing_target(self.sub_doc, "../Target.md"))

    def test_links_with_anchors_and_titles(self):
        self.assertIsNone(check_links.missing_target(self.doc, "Target.md#section"))
        self.assertIsNone(check_links.missing_target(self.doc, 'Target.md "Title"'))
        self.assertIsNone(check_links.missing_target(self.doc, 'Target.md#section "Title"'))

    def test_case_mismatch_fails(self):
        # 檔名大小寫不符
        res_lower = check_links.missing_target(self.doc, "target.md")
        self.assertIsNotNone(res_lower)
        self.assertIn("case mismatch", res_lower)

        res_upper = check_links.missing_target(self.doc, "TARGET.MD")
        self.assertIsNotNone(res_upper)
        self.assertIn("case mismatch", res_upper)

        # 目錄大小寫不符
        res_sub_dir = check_links.missing_target(self.doc, "SUB/Nested.md")
        self.assertIsNotNone(res_sub_dir)
        self.assertIn("case mismatch", res_sub_dir)

        # 子檔名大小寫不符
        res_sub_file = check_links.missing_target(self.doc, "sub/nested.md")
        self.assertIsNotNone(res_sub_file)
        self.assertIn("case mismatch", res_sub_file)

        # 相對父目錄跳轉的大小寫不符
        res_parent = check_links.missing_target(self.sub_doc, "../target.md")
        self.assertIsNotNone(res_parent)
        self.assertIn("case mismatch", res_parent)

        # 帶錨點但大小寫不符
        res_anchor = check_links.missing_target(self.doc, "target.md#section")
        self.assertIsNotNone(res_anchor)
        self.assertIn("case mismatch", res_anchor)

    def test_missing_target_fails(self):
        res = check_links.missing_target(self.doc, "NonExistent.md")
        self.assertIsNotNone(res)
        self.assertIn("missing", res)

    def test_skip_prefixes(self):
        self.assertIsNone(check_links.missing_target(self.doc, "https://example.com"))
        self.assertIsNone(check_links.missing_target(self.doc, "http://example.com"))
        self.assertIsNone(check_links.missing_target(self.doc, "mailto:user@example.com"))
        self.assertIsNone(check_links.missing_target(self.doc, "#local-anchor"))

    def test_check_document(self):
        test_file = self.dir / "test_doc.md"
        content = (
            "[ok](Target.md)\n"
            "[bad_case](target.md)\n"
            "[missing](nonexistent.md)\n"
            "![bad_img](sub/nested.md)\n"
            '<img src="SUB/Nested.md">\n'
            "[external](https://example.com)\n"
        )
        test_file.write_text(content, encoding="utf-8")
        problems = check_links.check_document(test_file)
        self.assertEqual(len(problems), 4)
        self.assertTrue(any("target.md" in p and "case mismatch" in p for p in problems))
        self.assertTrue(any("nonexistent.md" in p and "missing" in p for p in problems))
        self.assertTrue(any("sub/nested.md" in p and "case mismatch" in p for p in problems))
        self.assertTrue(any("SUB/Nested.md" in p and "case mismatch" in p for p in problems))


class SimulatedLinuxCheckLinksTests(CheckLinksTests):
    """模擬 Linux（大小寫敏感、resolve 不變更磁碟大小寫）環境下的測試。"""

    def setUp(self):
        super().setUp()
        self._orig_resolve = Path.resolve
        self._orig_exists = Path.exists

        orig_exists = self._orig_exists

        def linux_resolve(path_obj, strict=False):
            # Linux 的 resolve 保留原始大小寫，不自動代換成磁碟上的實際大小寫
            return Path(os.path.abspath(str(path_obj)))

        def linux_exists(path_obj):
            # Linux 的 exists 為大小寫敏感
            if not orig_exists(path_obj):
                return False
            p = Path(os.path.abspath(str(path_obj)))
            parts = p.parts
            cur = Path(parts[0])
            for part in parts[1:]:
                try:
                    entries = os.listdir(cur)
                except OSError:
                    return False
                if part not in entries:
                    return False
                cur = cur / part
            return True

        self.patch_resolve = unittest.mock.patch.object(Path, "resolve", linux_resolve)
        self.patch_exists = unittest.mock.patch.object(Path, "exists", linux_exists)
        self.patch_resolve.start()
        self.patch_exists.start()

    def tearDown(self):
        self.patch_exists.stop()
        self.patch_resolve.stop()
        super().tearDown()


if __name__ == "__main__":
    unittest.main()
