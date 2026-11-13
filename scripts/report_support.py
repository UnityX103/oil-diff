"""Shared file policy, compact summaries, and template selector expansion."""
from __future__ import annotations

from copy import deepcopy
from fnmatch import fnmatchcase


def is_path_only(file: dict[str, object] | str) -> bool:
    path = str(file.get("path", "")) if isinstance(file, dict) else file
    return path.lower().endswith((".prefab", ".prefab.meta")) or (
        isinstance(file, dict) and file.get("contentMode") == "path-only"
    )


def content_mode(file: dict[str, object]) -> str:
    if is_path_only(file):
        return "path-only"
    return "binary" if file.get("binary") else "text"


def build_summary(data: dict[str, object]) -> dict[str, object]:
    records = []
    for file in data.get("files", []):
        mode = content_mode(file)
        record = {key: file[key] for key in ("id", "status", "add", "delete")}
        record["contentMode"] = mode
        if file.get("countsKnown") is False:
            record["countsKnown"] = False
        if mode == "text":
            chunks = file.get("chunks", [])
            record["hunkCount"] = len(chunks)
            record["locations"] = list(dict.fromkeys(str(c["location"]) for c in chunks))[:3]
        records.append(record)
    return {
        "repoName": data.get("repoName"),
        "branch": data.get("branch"),
        "ranges": data.get("ranges", {}),
        "uniquePaths": data.get("uniquePaths", 0),
        "fileRecords": len(records),
        "pathOnlyRecords": sum(r["contentMode"] == "path-only" for r in records),
        "files": records,
    }


def select_files(data: dict[str, object], selectors: list[str]) -> list[str]:
    """Resolve exact IDs, repo-relative paths, or shell globs in stable data order."""
    if not isinstance(selectors, list) or any(not isinstance(s, str) for s in selectors):
        raise ValueError("'files' must be an array of file IDs, paths, or glob patterns.")
    files = data.get("files", [])
    ids = {str(file["id"]) for file in files}
    paths = {str(file["path"]) for file in files}
    selected: set[str] = set()
    for selector in selectors:
        if selector in ids:
            matches = [selector]
        elif selector in paths:
            matches = [str(file["id"]) for file in files if str(file["path"]) == selector]
        else:
            matches = [str(file["id"]) for file in files if fnmatchcase(str(file["path"]), selector)]
        if not matches:
            raise ValueError(f"File selector matched no changed files: {selector!r}")
        selected.update(matches)
    return [str(file["id"]) for file in files if str(file["id"]) in selected]


def expand_spec(data: dict[str, object], spec: dict[str, object]) -> dict[str, object]:
    """Accept compact 'files' selectors alongside the existing explicit schema."""
    result = deepcopy(spec)
    known = {str(file["id"]) for file in data.get("files", [])}
    for item in result.get("items", []):
        ids = list(item.get("fileIds", []))
        ids.extend(select_files(data, item.get("files", [])))
        for point in item.get("points", []):
            if not isinstance(point, dict) or "files" not in point:
                continue
            diffs = point.setdefault("diffs", [])
            existing = {str(diff["file"]) for diff in diffs}
            for fid in select_files(data, point["files"]):
                if fid not in existing:
                    diffs.append({"file": fid})
                ids.append(fid)
        item["fileIds"] = list(dict.fromkeys(ids))
        unknown = set(item["fileIds"]) - known
        if unknown:
            raise ValueError(f"Unknown file IDs: {sorted(unknown)}")
    return result
