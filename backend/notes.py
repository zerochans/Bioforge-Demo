from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_OBSIDIAN_DIR = "/media/h3c/Win11Pro X64/data/literature/obsidian/00-BioForge"
OBSIDIAN_DIR = Path(os.environ.get("BIOFORGE_OBSIDIAN_DIR", DEFAULT_OBSIDIAN_DIR)).expanduser()
MAX_BYTES = 2_000_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _root() -> Path:
    return OBSIDIAN_DIR.resolve()


def _safe(relative: str) -> Path:
    clean = (relative or "").replace("\\", "/").lstrip("/")
    if not clean or ".." in clean.split("/"):
        raise ValueError("invalid note path")
    root = _root()
    path = (root / clean).resolve()
    if path != root and root not in path.parents:
        raise ValueError("note path escapes the vault")
    if path.suffix.lower() != ".md":
        raise ValueError("only Markdown notes are readable")
    return path


def _title(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:4000]
    except OSError:
        return path.stem
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()[:160]
        if stripped.lower().startswith("title:"):
            return stripped.split(":", 1)[1].strip().strip('"')[:160]
    return path.stem


def status() -> dict[str, Any]:
    root = _root()
    notes = list_notes() if root.exists() else []
    return {
        "root": str(root),
        "exists": root.exists(),
        "count": len(notes),
        "latest": notes[:1],
        "mode": "read-only",
        "checked_at": _now(),
        "note": "浏览器只能读取 Markdown；无法嵌入 Obsidian 桌面 UI。修改请回到 Obsidian。",
    }


def list_notes(limit: int = 200) -> list[dict[str, Any]]:
    root = _root()
    if not root.exists():
        return []
    items = []
    for path in root.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        items.append({
            "path": path.relative_to(root).as_posix(),
            "title": _title(path),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
        })
    items.sort(key=lambda item: item["modified"], reverse=True)
    return items[: max(1, min(1000, limit))]


def read_note(relative: str) -> dict[str, Any]:
    path = _safe(relative)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(relative)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("note is too large to display (max 2 MB)")
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {
        "path": path.relative_to(_root()).as_posix(),
        "title": _title(path),
        "text": text,
        "size": len(text.encode("utf-8")),
        "modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
        "mode": "read-only",
        "checked_at": _now(),
    }
