from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import data

RESOURCE_PATH = data.DATA_DIR / "resources.json"


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    with RESOURCE_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    groups = payload.get("groups", [])
    items = [item for group in groups for item in group.get("items", [])]
    return {
        **payload,
        "counts": {
            "groups": len(groups),
            "items": len(items),
            "live": sum(1 for item in items if item.get("status") == "live"),
            "link_only": sum(1 for item in items if item.get("status") == "link_only"),
            "licensed": sum(1 for item in items if item.get("status") == "license_required"),
            "institution": sum(1 for item in items if item.get("status") == "institution_login"),
        },
    }
