#!/usr/bin/env python3
"""End-to-end unit tests for the oil-diff Skill scripts."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required to run test_oil_diff.py.")

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"


def run_cmd(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


class CodePreviewTests(unittest.TestCase):
    def test_source_text_and_rider_tokens(self):
        import importlib.util
        import html
        import re
        spec = importlib.util.spec_from_file_location("oil_renderer", SCRIPTS_DIR / "render_report.py")
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        source = '    public bool enabled = false; // <safe> & exact'
        rendered = renderer.syntax_text(source, "Example.cs")
        self.assertEqual(html.unescape(re.sub(r"<[^>]*>", "", rendered)), source)
        self.assertIn('class="tok-keyword"', rendered)
        self.assertIn('class="tok-comment"', rendered)
        css = renderer.rider_css()
        self.assertIn("data:font/woff2;base64,", css)
        self.assertNotIn('url("fonts/', css)
        self.assertIn("SIL OPEN FONT LICENSE", css)

    def test_single_column_changed_source_and_deleted_lines(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("oil_renderer_single", SCRIPTS_DIR / "render_report.py")
        renderer = importlib.util.module_from_spec(spec); spec.loader.exec_module(renderer)
        f = {"path":"x.md", "beforeText":"start\nold\nend\n", "afterText":"start\nnew\nend\n"}
        output = renderer.single_source_html(f, 2)
        self.assertNotIn('data-line="3"', output)
        self.assertNotIn('data-line="1"', output)
        self.assertIn('data-line="2"', output)
        self.assertIn('code-line modified', output)
        self.assertIn('deleted-code', output)
        self.assertNotIn('compare-side', output)
        self.assertIn('data-focus-line="2"', output)
        with self.assertRaises(ValueError): renderer.single_source_html({"path":"legacy.cs"})

    def render_method_change(self, path, before, after):
        import importlib.util
        spec = importlib.util.spec_from_file_location("oil_renderer_methods", SCRIPTS_DIR / "render_report.py")
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        return renderer.single_source_html({"path": path, "beforeText": before, "afterText": after})

    def visible_rows(self, output):
        """Extract exact target source text, excluding line-number buttons and old code."""
        from html.parser import HTMLParser
        class Rows(HTMLParser):
            def __init__(self):
                super().__init__()
                self.rows = {}
                self.line = None
                self.depth = 0
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if 'data-line' in attrs:
                    self.line = int(attrs['data-line'])
                if self.depth:
                    self.depth += 1
                elif attrs.get('class') == 'line-text' and self.line is not None:
                    self.depth = 1
                    self.rows[self.line] = ''
            def handle_endtag(self, tag):
                if self.depth:
                    self.depth -= 1
            def handle_data(self, data):
                if self.depth:
                    self.rows[self.line] += data
        parser = Rows()
        parser.feed(output.split('<details class="deleted-code">', 1)[0])
        return parser.rows

    def test_csharp_preview_keeps_complete_changed_method_and_excludes_neighbors(self):
        before = '''class Demo
{
    public void Update()
    {
        Prepare();
        if (ready)
        {
            RunOld();
        }
        Finish();
    }

    public void Unrelated()
    {
        LeaveAlone();
    }
}
'''
        after = before.replace('RunOld();', 'RunNew();')
        output = self.render_method_change('Demo.cs', before, after)
        rows = self.visible_rows(output)
        self.assertEqual(list(rows), list(range(3, 12)))
        self.assertEqual(list(rows.values()), after.splitlines()[2:11])
        self.assertIn('data-line="5" data-state="unchanged"', output)
        self.assertIn('data-line="8" data-state="modified"', output)
        self.assertNotIn('LeaveAlone', output)

    def test_python_decorators_multiline_signature_and_nested_operation(self):
        before = '''@trace("context")
async def load(
    path: str,
):
    def normalize(value):
        return value.strip()
    result = normalize(path)
    return result

def unrelated():
    return "keep hidden"
'''
        after = before.replace('value.strip()', 'value.strip().lower()')
        rows = self.visible_rows(self.render_method_change('example.py', before, after))
        self.assertEqual(list(rows), list(range(1, 9)))
        self.assertEqual(list(rows.values()), after.splitlines()[:8])

    def test_multiple_changed_methods_are_complete_without_duplicate_context(self):
        before = '''class Demo {
    void First() {
        Prepare();
        OldFirst();
        Finish();
    }
    void Hidden() {
        Ignore();
    }
    void Second() {
        Prepare();
        OldSecond();
        Finish();
    }
}
'''
        after = before.replace('OldFirst()', 'NewFirst()').replace('OldSecond()', 'NewSecond()')
        output = self.render_method_change('Demo.cs', before, after)
        rows = self.visible_rows(output)
        self.assertEqual(list(rows), list(range(2, 7)) + list(range(10, 15)))
        self.assertEqual(output.count('省略无关方法或文件内容'), 1)

    def test_deleting_statement_keeps_surviving_method_but_deleted_method_stays_old(self):
        before = '''class Demo {
    void First() {
        Prepare();
        Remove();
        Finish();
    }
    void Second() {
        Unrelated();
    }
}
'''
        after = before.replace('        Remove();\n', '')
        rows = self.visible_rows(self.render_method_change('Demo.cs', before, after))
        self.assertEqual(list(rows), list(range(2, 6)))
        after = before.replace('    void First() {\n        Prepare();\n        Remove();\n        Finish();\n    }\n', '')
        self.assertEqual(self.visible_rows(self.render_method_change('Demo.cs', before, after)), {})

    def test_new_method_includes_full_signature_and_body(self):
        before = 'class Demo {\n}\n'
        after = 'class Demo {\n    public void Added() {\n        Prepare();\n        Run();\n    }\n}\n'
        rows = self.visible_rows(self.render_method_change('Demo.cs', before, after))
        self.assertEqual(list(rows.values()), after.splitlines()[1:5])

    def test_braces_in_comments_strings_and_js_regex_do_not_cut_methods(self):
        samples = {
            'Demo.cs': '''class Demo {
    [Trace("}")]
    public void Run() {
        var example = @"}""{";
        // } misleading brace
        /* { misleading brace */
        Old();
        Finish();
    }
    void Hidden() { Ignore(); }
}
''',
            'demo.js': '''const run = (input) => {
    const pattern = /[{}]/g;
    const sample = '}' + '{';
    Old();
    return input.replace(pattern, sample);
};
function hidden() { return 0; }
''',
        }
        for path, before in samples.items():
            with self.subTest(path=path):
                after = before.replace('Old()', 'New()')
                output = self.render_method_change(path, before, after)
                rows = self.visible_rows(output)
                self.assertNotIn('无法可靠识别', output)
                self.assertIn('Finish();' if path.endswith('.cs') else 'return input.replace(pattern, sample);', '\n'.join(rows.values()))
                self.assertNotIn('Ignore();' if path.endswith('.cs') else 'function hidden', '\n'.join(rows.values()))

    def test_expression_method_and_unsupported_code_fallback_preserve_full_body(self):
        before = 'class Demo {\n    int Count() =>\n        Old();\n    void Hidden() { Ignore(); }\n}\n'
        after = before.replace('Old()', 'New()')
        rows = self.visible_rows(self.render_method_change('Demo.cs', before, after))
        self.assertEqual(list(rows.values()), after.splitlines()[1:3])
        before = 'def run\n  prepare\n  old\n  finish\nend\n'
        after = before.replace('old', 'updated')
        output = self.render_method_change('demo.rb', before, after)
        self.assertIn('无法可靠识别完整方法边界', output)
        self.assertEqual(list(self.visible_rows(output).values()), after.splitlines())

    def test_nested_interpolation_never_truncates_changed_method(self):
        samples = {
            'Demo.cs': 'class Demo {\n void Run() {\n  var value = $"Value {Call(\"}\", \"{\")}";\n  Finish();\n }\n}\n',
            'demo.js': 'function run() {\n const value = `outer ${fn(`nested }`, "{")}`;\n Finish();\n}\n',
            'regex.js': 'function run() {\n if (ready) /}{/.test(value);\n Finish();\n}\n',
        }
        for path, before in samples.items():
            with self.subTest(path=path):
                after = before.replace('value =', 'updated =').replace('test(value)', 'test(updated)')
                output = self.render_method_change(path, before, after)
                self.assertIn('无法可靠识别完整方法边界', output)
                self.assertEqual(list(self.visible_rows(output).values()), after.splitlines())

    def test_drawer_path_is_not_truncated(self):
        css = (SKILL_ROOT / "assets/report.css").read_text()
        rule = css.split(".drawer-file-identity strong{", 1)[1].split("}", 1)[0]
        for value in ("max-width:none", "white-space:normal", "overflow:visible", "overflow-wrap:anywhere"):
            self.assertIn(value, rule)


class OilDiffWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        run_cmd(["git", "init"], self.repo)
        run_cmd(["git", "config", "user.email", "tester@example.com"], self.repo)
        run_cmd(["git", "config", "user.name", "Tester"], self.repo)

        (self.repo / "SKILL.md").write_text(
            "# Demo Skill\n\n## Flow\nOld single step.\n",
            encoding="utf-8",
        )
        (self.repo / "references").mkdir()
        (self.repo / "references" / "guide.md").write_text(
            "# Guide\n\nInitial rule line.\n",
            encoding="utf-8",
        )
        (self.repo / "README.md").write_text(
            "# Demo\n\nOld summary.\n",
            encoding="utf-8",
        )
        run_cmd(["git", "add", "."], self.repo)
        run_cmd(["git", "commit", "-m", "Initial commit"], self.repo)

        # Modify files in working tree
        (self.repo / "SKILL.md").write_text(
            "# Demo Skill\n\n## Flow\nNew merged two-step check.\n",
            encoding="utf-8",
        )
        (self.repo / "references" / "guide.md").write_text(
            "# Guide\n\nUpdated rule line with clear boundary.\n",
            encoding="utf-8",
        )
        (self.repo / "README.md").write_text(
            "# Demo\n\nUpdated summary for users.\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_collect_render_and_lint_pipeline(self) -> None:
        out_dir = self.repo / ".oil-diff"
        collect_res = run_cmd(
            [
                sys.executable,
                str(SCRIPTS_DIR / "collect_diff.py"),
                "--repo",
                str(self.repo),
                "--output",
                str(out_dir),
            ],
            cwd=self.repo,
        )
        summary = json.loads(collect_res.stdout)
        self.assertEqual(summary["uniquePaths"], 3)
        self.assertTrue((out_dir / ".gitignore").is_file())
        self.assertEqual((out_dir / ".gitignore").read_text(encoding="utf-8"), "*\n")

        spec = {
            "title": "这次修改了哪 1 件事",
            "eyebrow": "demo-skill / 改动汇报",
            "summary": "调整了主流程与参考说明文档，让规则边界更清晰。",
            "items": [
                {
                    "number": 1,
                    "module": "主流程与说明规范",
                    "navLabel": "合并主流程检查",
                    "title": "优化了主流程说明，把原本分散的检查步骤合并到同一处",
                    "overview": "把主流程说明里的检查步骤合并到一处，并同步更新参考文档。",
                    "fileIds": [
                        "working:SKILL.md",
                        "working:references/guide.md",
                        "working:README.md",
                    ],
                    "points": [
                        {
                            "title": "主流程改为合并检查",
                            "copy": "只改了主入口文件时，卡片不再重复显示第二行单文件说明。",
                            "diffs": [
                                {
                                    "file": "working:SKILL.md",
                                    "role": "更新主入口中的检查步骤描述。",
                                    "before": [{"line": 4}],
                                    "after": [{"line": 4}],
                                }
                            ],
                        },
                        {
                            "title": "同步更新主入口与参考说明",
                            "copy": "涉及多个文件时，卡片保留每个文件的职责说明。",
                            "diffs": [
                                {
                                    "file": "working:SKILL.md",
                                    "role": "入口文档写明合并后的检查要求。",
                                    "before": [{"line": 4}],
                                    "after": [{"line": 4}],
                                },
                                {
                                    "file": "working:references/guide.md",
                                    "role": "详细说明文档补充边界条件。",
                                    "before": [{"line": 3}],
                                    "after": [{"line": 3}],
                                },
                            ],
                        },
                    ],
                    "relatedTitle": "查看其余 {count} 个文件的对应修改",
                }
            ],
        }
        spec_path = out_dir / "assets" / "report-spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

        html_path = out_dir / "index.html"
        run_cmd(
            [
                sys.executable,
                str(SCRIPTS_DIR / "render_report.py"),
                "--report-dir",
                str(out_dir),
            ],
            cwd=self.repo,
        )
        self.assertTrue(html_path.is_file())
        html_text = html_path.read_text(encoding="utf-8")
        self.assertIn('class="bg-grid"', html_text)
        self.assertIn('class="diff-drawer-root"', html_text)
        self.assertIn('blast-funnel', html_text)
        self.assertIn('id="bento-deck"', html_text)
        self.assertIn('id="shot-lightbox"', html_text)
        self.assertIn('id="related-1"', html_text)
        self.assertNotIn('id="all-files"', html_text)
        self.assertNotIn('<details class="diff-card"', html_text)

        lint_res = run_cmd(
            [
                sys.executable,
                str(SCRIPTS_DIR / "lint_report.py"),
                "--repo",
                str(self.repo),
                "--report-dir",
                str(out_dir),
            ],
            cwd=self.repo,
        )
        self.assertIn("PASS: 0 errors", lint_res.stdout)

        # Verify stray top-level file is rejected by lint_report.py
        stray_file = out_dir / "stray-screenshot.png"
        stray_file.write_text("dummy", encoding="utf-8")
        stray_proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "lint_report.py"),
                "--repo",
                str(self.repo),
                "--report-dir",
                str(out_dir),
            ],
            cwd=self.repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertNotEqual(stray_proc.returncode, 0)
        self.assertIn("move stray files into assets/", stray_proc.stdout)

    def test_lint_catches_hype_words(self) -> None:
        out_dir = self.repo / ".oil-diff"
        run_cmd(
            [
                sys.executable,
                str(SCRIPTS_DIR / "collect_diff.py"),
                "--repo",
                str(self.repo),
                "--output",
                str(out_dir),
            ],
            cwd=self.repo,
        )
        bad_spec = {
            "title": "这次修改了哪 1 件事",
            "summary": "通过组合拳赋能业务闭环。",
            "items": [
                {
                    "number": 1,
                    "module": "主流程",
                    "navLabel": "主流程",
                    "title": "优化了主流程说明与文件规则",
                    "overview": "优化了主流程说明与文件规则，确保上下游一致。",
                    "fileIds": [
                        "working:SKILL.md",
                        "working:references/guide.md",
                        "working:README.md",
                    ],
                    "points": [],
                }
            ],
        }
        spec_path = out_dir / "assets" / "report-spec.json"
        spec_path.write_text(json.dumps(bad_spec, ensure_ascii=False), encoding="utf-8")
        html_path = out_dir / "index.html"
        run_cmd(
            [
                sys.executable,
                str(SCRIPTS_DIR / "render_report.py"),
                "--data",
                str(out_dir / "assets" / "diff-data.json"),
                "--spec",
                str(spec_path),
                "--output",
                str(html_path),
            ],
            cwd=self.repo,
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "lint_report.py"),
                "--repo",
                str(self.repo),
                "--report-dir",
                str(out_dir),
            ],
            cwd=self.repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Forbidden hype/jargon word", proc.stdout)

    def test_structured_diagrams_and_plain_text_diagram_lint(self) -> None:
        out_dir = self.repo / ".oil-diff"
        run_cmd(
            [
                sys.executable,
                str(SCRIPTS_DIR / "collect_diff.py"),
                "--repo",
                str(self.repo),
                "--output",
                str(out_dir),
            ],
            cwd=self.repo,
        )
        for dtype in ("routing", "comparison", "scenarios", "flow", "alignment", "diagnostics", "screenshots", "schema"):
            spec = {
                "title": "这次修改了哪 1 件事",
                "summary": "调整了主流程说明与文件边界。",
                "items": [
                    {
                        "number": 1,
                        "module": "主流程",
                        "navLabel": "主流程",
                        "title": "优化了主流程说明与文件规则",
                        "overview": "优化了主流程说明与文件规则，确保上下游一致。",
                        "problem": "以前只有一份总说明，找起来费劲。",
                        "example": "比如只改一处说明时还要翻完整篇文档。",
                        "diagram": {
                            "type": dtype,
                            "mode": "slider",
                            "captureSource": "live-capture",
                            "before": {"src": "assets/shots/before.png", "title": "修改前", "tag": "× 旧界面"},
                            "after": {"src": "assets/shots/after.png", "title": "修改后", "tag": "✓ 新界面"},
                            "branches": [{"title": "分支 A", "file": "SKILL.md", "copy": "说明"}],
                            "scenarios": [{"title": "场景 A", "before": "以前", "after": "现在"}],
                            "rows": [{"title": "检查 1", "file": "SKILL.md", "detail": "锚点", "verdict": "通过", "pass": True}],
                        },
                        "fileIds": [
                            "working:SKILL.md",
                            "working:references/guide.md",
                            "working:README.md",
                        ],
                        "points": [],
                    }
                ],
            }
            spec_path = out_dir / "assets" / "report-spec.json"
            spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            run_cmd(
                [sys.executable, str(SCRIPTS_DIR / "render_report.py"), "--report-dir", str(out_dir)],
                cwd=self.repo,
            )
            lint_res = run_cmd(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "lint_report.py"),
                    "--repo",
                    str(self.repo),
                    "--report-dir",
                    str(out_dir),
                ],
                cwd=self.repo,
            )
            self.assertIn("PASS: 0 errors", lint_res.stdout)

    def test_lint_blocks_scavenged_repo_screenshots_and_missing_capture_source(self) -> None:
        out_dir = self.repo / ".oil-diff"
        run_cmd(
            [
                sys.executable,
                str(SCRIPTS_DIR / "collect_diff.py"),
                "--repo",
                str(self.repo),
                "--output",
                str(out_dir),
            ],
            cwd=self.repo,
        )

        # Simulate a gitignored/untracked research directory in the repo with an online reference image
        work_dir = self.repo / "_work" / "research"
        work_dir.mkdir(parents=True)
        fake_png = work_dir / "online-ref.png"
        fake_png.write_bytes(b"\x89PNG\r\n\x1a\nFAKE_RESEARCH_IMAGE_PAYLOAD")

        # Copy the fake research image into .oil-diff/assets/shots/
        shots_dir = out_dir / "assets" / "shots"
        shots_dir.mkdir(parents=True, exist_ok=True)
        (shots_dir / "copied-ref.png").write_bytes(fake_png.read_bytes())

        spec = {
            "title": "这次修改了哪 1 件事",
            "summary": "调整了主流程说明与文件边界。",
            "items": [
                {
                    "number": 1,
                    "module": "主流程",
                    "navLabel": "主流程",
                    "title": "优化了主流程说明与文件规则",
                    "overview": "优化了主流程说明与文件规则，确保上下游一致。",
                    "diagram": {
                        "type": "screenshots",
                        "mode": "grid",
                        "shots": [{"src": "assets/shots/copied-ref.png", "title": "假实拍图"}],
                    },
                    "fileIds": [
                        "working:SKILL.md",
                        "working:references/guide.md",
                        "working:README.md",
                    ],
                    "points": [],
                }
            ],
        }
        spec_path = out_dir / "assets" / "report-spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        run_cmd(
            [sys.executable, str(SCRIPTS_DIR / "render_report.py"), "--report-dir", str(out_dir)],
            cwd=self.repo,
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "lint_report.py"),
                "--repo",
                str(self.repo),
                "--report-dir",
                str(out_dir),
            ],
            cwd=self.repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("without a valid 'captureSource'", proc.stdout)
        self.assertIn("same SHA-256 as unchanged/untracked repo image", proc.stdout)

    def test_chinese_filenames_and_binary_files_and_single_hunk_excerpts(self) -> None:
        # Create a Chinese-named file and an untracked binary file
        (self.repo / "设计说明.md").write_text("# 标题\n第一行\n第二行\n第三行\n", encoding="utf-8")
        (self.repo / "logo.bin").write_bytes(b"\x00\x01\x02\x03BINARY_ASSET")
        out_dir = self.repo / ".oil-diff"
        collect_res = run_cmd(
            [
                sys.executable,
                str(SCRIPTS_DIR / "collect_diff.py"),
                "--repo",
                str(self.repo),
                "--output",
                str(out_dir),
            ],
            cwd=self.repo,
        )
        summary = json.loads(collect_res.stdout)
        self.assertEqual(summary["uniquePaths"], 5)
        diff_data = json.loads((out_dir / "assets" / "diff-data.json").read_text(encoding="utf-8"))
        by_path = {f["path"]: f for f in diff_data["files"]}
        self.assertIn("设计说明.md", by_path)
        self.assertFalse(by_path["设计说明.md"]["binary"])
        self.assertTrue(len(by_path["设计说明.md"]["chunks"]) > 0)
        self.assertIn("logo.bin", by_path)
        self.assertTrue(by_path["logo.bin"]["binary"])
        self.assertEqual(by_path["logo.bin"]["chunks"], [])


if __name__ == "__main__":
    unittest.main()
