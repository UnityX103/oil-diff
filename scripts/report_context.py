#!/usr/bin/env python3
"""Read bounded agent context and seed a report spec from the built-in template."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

from report_support import build_summary, content_mode

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "report-spec.template.json"


def init_spec(report_dir: Path, data: dict[str, object]) -> bool:
    target = report_dir / "assets" / "report-spec.json"
    if target.exists():
        return False
    spec = deepcopy(json.loads(TEMPLATE.read_text(encoding="utf-8")))
    spec["eyebrow"] = f'{data.get("repoName", "repo")} / 改动汇报'
    if data.get("files") and all(content_mode(file) == "path-only" for file in data["files"]):
        spec["items"][0]["diagram"] = {"type": "targets"}
    target.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def inspect_file(data: dict[str, object], selector: str, offset: int, limit: int) -> dict[str, object]:
    files = [file for file in data["files"] if selector in (file["id"], file["path"])]
    if not files:
        raise ValueError(f"Unknown changed file: {selector!r}")
    records = []
    rows = []
    for file in files:
        mode = content_mode(file)
        records.append({"id": file["id"], "status": file["status"], "contentMode": mode})
        if mode == "path-only":
            records[-1]["notice"] = "预制体仅列目标，不分析内容变更。"
            continue
        if mode == "binary":
            continue
        for chunk in file.get("chunks", []):
            rows.append({"file": file["id"], "hunk": chunk["number"], "location": chunk["location"]})
            for side in ("before", "after"):
                for row in chunk.get(side, []):
                    if side == "before" and not row["changed"]:
                        continue
                    prefix = "-" if side == "before" else "+" if row["changed"] else " "
                    text = str(row["text"])
                    rows.append({"side": prefix, "line": row["line"], "text": text[:500],
                                 **({"truncated": True} if len(text) > 500 else {})})
    end = offset + limit
    return {"files": records, "totalRows": len(rows), "offset": offset,
            "rows": rows[offset:end], "nextOffset": end if end < len(rows) else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--init-spec", action="store_true", help="Seed report-spec.json only if it does not exist.")
    parser.add_argument("--file", help="Inspect one exact file ID or path; Prefabs never return content.")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=60, help="Maximum summary records (default 60).")
    parser.add_argument("--max-lines", type=int, default=80, help="Maximum diff rows (default 80).")
    args = parser.parse_args()
    if args.offset < 0 or args.limit < 1 or args.max_lines < 1:
        parser.error("offset must be >= 0; limit and max-lines must be >= 1.")
    report_dir = Path(args.report_dir).resolve()
    data = json.loads((report_dir / "assets" / "diff-data.json").read_text(encoding="utf-8"))
    try:
        if args.file:
            result = inspect_file(data, args.file, args.offset, args.max_lines)
        else:
            result = build_summary(data)
            end = args.offset + args.limit
            result["files"] = result["files"][args.offset:end]
            result["offset"] = args.offset
            result["nextOffset"] = end if end < result["fileRecords"] else None
        if args.init_spec:
            result["specCreated"] = init_spec(report_dir, data)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
