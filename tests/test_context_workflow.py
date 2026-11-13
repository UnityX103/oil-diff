"""Regression coverage for path-only Prefabs and the compact template workflow."""
from __future__ import annotations

from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import collect_diff as collector
import lint_report as linter
import render_report as renderer
import report_context
from report_support import build_summary, expand_spec, is_path_only, select_files


class CompactWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.out = self.repo / ".oil-diff"
        self.git("init")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "测试")
        for path in ("Assets/Changed.prefab", "Assets/Deleted.prefab", "Assets/Old.prefab", "Assets/Changed.prefab.meta"):
            self.write(path, "PRIVATE_PREFAB_OLD\n")
        self.write("src/Queue.cs", "class Queue {\n  public int Count() {\n    return 1;\n  }\n}\n")
        self.write("Assets/Settings.asset", "text: old\n")
        self.git("add", ".")
        self.git("commit", "-m", "初始化测试资源")
        self.write("Assets/Changed.prefab", "PRIVATE_PREFAB_NEW\n" * 200)
        self.write("Assets/Changed.prefab.meta", "PRIVATE_META_NEW\n")
        (self.repo / "Assets/Deleted.prefab").unlink()
        (self.repo / "Assets/Old.prefab").rename(self.repo / "Assets/Moved.prefab")
        self.write("Assets/New.PREFAB", "PRIVATE_PREFAB_NEW_UNTRACKED\n")
        self.write("src/Queue.cs", "class Queue {\n  public int Count() {\n    return 2;\n  }\n}\n")
        self.write("Assets/Settings.asset", "text: new\n")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, text=True, capture_output=True, check=True).stdout

    def write(self, path, text):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def collect(self):
        return collector.collect_diff(self.repo, self.out, ["working:本轮:HEAD..WT"])

    def spec(self):
        return {
            "title": "任务队列及关联资源改动汇报",
            "summary": "任务队列返回值与配置更新，预制体只列变更目标。",
            "items": [{
                "module": "任务队列",
                "title": "任务队列：调整返回值并同步关联资源",
                "overview": "队列返回值由一调整为二；关联预制体只列目标，不分析内容。",
                "files": ["*"],
                "diagram": {"type": "targets"},
                "points": [{"title": "更新队列与重要目标", "files": ["src/Queue.cs", "Assets/Changed.prefab"]}],
            }],
        }

    def test_prefab_collection_never_reads_contents_and_preserves_git_state(self):
        status, head = self.git("status", "--short"), self.git("rev-parse", "HEAD")
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if is_path_only(path.as_posix()):
                raise AssertionError(f"Prefab content was read: {path}")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", guarded_open):
            data = self.collect()
        metadata = [file for file in data["files"] if is_path_only(file)]
        self.assertEqual(len(metadata), 6)
        self.assertEqual({file["kind"] for file in metadata}, {"A", "M", "D"})
        for file in metadata:
            self.assertEqual(file["contentMode"], "path-only")
            self.assertEqual(file["chunks"], [])
            self.assertNotIn("beforeText", file)
            self.assertNotIn("afterText", file)
        self.assertFalse(next(file for file in metadata if file["path"] == "Assets/New.PREFAB")["countsKnown"])
        config = next(file for file in data["files"] if file["path"].endswith(".asset"))
        self.assertEqual(config["afterText"], "text: new\n")
        self.assertEqual(self.git("status", "--short"), status)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_summary_and_inspector_do_not_expose_prefab_or_full_source(self):
        data = self.collect()
        summary = json.loads((self.out / "assets/change-summary.json").read_text())
        self.assertEqual(summary, build_summary(data))
        serialized = json.dumps(summary)
        self.assertNotIn("PRIVATE_", serialized)
        self.assertNotIn("return 2;", serialized)
        info = report_context.inspect_file(data, "Assets/Changed.prefab", 0, 80)
        self.assertEqual(info["rows"], [])
        self.assertEqual(info["files"][0]["contentMode"], "path-only")
        code = report_context.inspect_file(data, "src/Queue.cs", 0, 2)
        self.assertEqual(len(code["rows"]), 2)
        self.assertEqual(code["nextOffset"], 2)
        continuation = report_context.inspect_file(data, "src/Queue.cs", 2, 80)
        self.assertIsNone(continuation["nextOffset"])
        self.assertTrue(any(row.get("text") == "    return 2;" and row["line"] == 3 for row in continuation["rows"]))

    def test_context_cli_pagination_and_template_do_not_overwrite_existing_spec(self):
        data = self.collect()
        script = SKILL_ROOT / "scripts/report_context.py"
        command = [sys.executable, str(script), "--report-dir", str(self.out), "--init-spec", "--limit", "2"]
        first = json.loads(subprocess.check_output(command, text=True))
        self.assertTrue(first["specCreated"])
        self.assertEqual(first["nextOffset"], 2)
        self.assertEqual(len(first["files"]), 2)
        spec_path = self.out / "assets/report-spec.json"
        draft = json.loads(spec_path.read_text())
        with self.assertRaisesRegex(ValueError, "_draft"):
            renderer.render_html_document(data, draft)
        spec_path.write_text(json.dumps(self.spec()), encoding="utf-8")
        before = spec_path.read_bytes()
        second = json.loads(subprocess.check_output(command + ["--offset", "2"], text=True))
        self.assertFalse(second["specCreated"])
        self.assertEqual(second["files"][0]["id"], build_summary(data)["files"][2]["id"])
        self.assertEqual(spec_path.read_bytes(), before)

    def test_compact_spec_renders_and_lints_without_yaml_and_keeps_full_code_method(self):
        data = self.collect()
        spec = self.spec()
        document = renderer.render_html_document(data, spec)
        self.assertNotIn("PRIVATE_", document)
        self.assertIn("预制体仅列目标，不分析内容变更", document)
        self.assertIn("部分资源未统计行数", document)
        self.assertIn("Assets/Changed.prefab", document)
        # Existing full-method code previews remain available for actual source files.
        self.assertIn("public", document)
        self.assertIn('data-line="2"', document)
        (self.out / "assets/report-spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        (self.out / "index.html").write_text(document, encoding="utf-8")
        errors, warnings = linter.lint_report(self.repo, self.out)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        # Legacy data is not exposed even before recollection, and lint requires migration.
        legacy = next(file for file in data["files"] if is_path_only(file))
        legacy["beforeText"] = "PRIVATE_LEGACY_PREFAB"
        legacy["chunks"] = [{"invalid": "must never be parsed"}]
        self.assertNotIn("PRIVATE_LEGACY_PREFAB", renderer.render_html_document(data, spec))
        (self.out / "assets/diff-data.json").write_text(json.dumps(data), encoding="utf-8")
        errors, _ = linter.lint_report(self.repo, self.out)
        self.assertTrue(any("Prefab content" in error for error in errors))

    def test_resource_only_template_and_drawer_never_request_source_navigation(self):
        data = self.collect()
        data["files"] = [file for file in data["files"] if is_path_only(file)]
        self.assertTrue(report_context.init_spec(self.out, data))
        spec = json.loads((self.out / "assets/report-spec.json").read_text())
        self.assertEqual(spec["items"][0]["diagram"], {"type": "targets"})
        for file in data["files"]:
            markup = renderer.single_source_html(file)
            self.assertNotIn("data-line", markup)
            self.assertNotIn("single-source", markup)

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for drawer interaction tests")
    def test_mixed_prefab_and_source_tree_does_not_block_drawer(self):
        data = self.collect()
        document = renderer.render_html_document(data, self.spec())

        class TreeRows(HTMLParser):
            def __init__(self):
                super().__init__()
                self.rows = []
                self.row = None

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "button" and attrs.get("class") == "tree-file":
                    self.row = {"path": attrs["data-path"], "add": None, "delete": None}
                    self.rows.append(self.row)
                if self.row is not None and tag in ("b", "i"):
                    self.row["add" if tag == "b" else "delete"] = "initial"

            def handle_endtag(self, tag):
                if tag == "button":
                    self.row = None

        parser = TreeRows()
        parser.feed(document)
        self.assertTrue(any(row["add"] is None for row in parser.rows))
        self.assertTrue(any(row["add"] is not None for row in parser.rows))
        payload = {"rows": parser.rows, "reading": data["reading"], "files": data["files"]}
        result = subprocess.run(
            [shutil.which("node"), str(SKILL_ROOT / "tests/drawer_interactions.cjs")],
            input=json.dumps(payload), capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_selectors_preserve_ranges_literal_paths_and_reject_unknown_patterns(self):
        data = {"files": [
            {"id": "working:src/a[1].cs", "path": "src/a[1].cs"},
            {"id": "committed:src/a[1].cs", "path": "src/a[1].cs"},
            {"id": "working:src/a1.cs", "path": "src/a1.cs"},
        ]}
        self.assertEqual(select_files(data, ["src/a[1].cs"]), ["working:src/a[1].cs", "committed:src/a[1].cs"])
        self.assertEqual(select_files(data, ["committed:src/a[1].cs"]), ["committed:src/a[1].cs"])
        spec = {"items": [{"files": ["src/*"], "points": [{"files": ["src/a1.cs"]}]}]}
        untouched = deepcopy(spec)
        expanded = expand_spec(data, spec)
        self.assertEqual(len(expanded["items"][0]["fileIds"]), 3)
        self.assertEqual(expanded["items"][0]["points"][0]["diffs"], [{"file": "working:src/a1.cs"}])
        self.assertEqual(spec, untouched)
        with self.assertRaises(ValueError):
            select_files(data, ["missing/*"])

    def test_inspector_bounds_long_lines_and_target_diagram_rejects_invented_files(self):
        data = self.collect()
        file = next(file for file in data["files"] if file["path"] == "src/Queue.cs")
        file["chunks"][0]["after"][0]["text"] = "x" * 1500
        info = report_context.inspect_file(data, file["id"], 0, 80)
        self.assertTrue(any(row.get("truncated") and len(row["text"]) == 500 for row in info["rows"]))
        spec = self.spec()
        spec["items"][0]["diagram"]["files"] = ["Assets/Unchanged.prefab"]
        with self.assertRaisesRegex(ValueError, "targets.files"):
            renderer.render_html_document(data, spec)


if __name__ == "__main__":
    unittest.main()
