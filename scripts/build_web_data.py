#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WEB = ROOT / "web"
ANDROID_WWW = ROOT / "android" / "app" / "src" / "main" / "assets" / "www"
FILES = ["proteins.json", "protectants.json", "compounds.json", "matrices.json", "spectra.json"]


def main() -> None:
    pack = {}
    for name in FILES:
        pack[name.split(".")[0]] = json.loads((DATA / name).read_text(encoding="utf-8"))
    payload = "window.BIOFORGE_DATA = " + json.dumps(pack, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (WEB / "data.js").write_text(payload, encoding="utf-8")
    print(f"wrote {WEB / 'data.js'} ({len(payload)} bytes)")
    if ANDROID_WWW.exists():
        for name in ["index.html", "styles.css", "app.js", "lab.js", "offline.js", "data.js", "i18n-data.js", "manifest.webmanifest", "sw.js"]:
            source = WEB / name
            if source.exists():
                shutil.copy2(source, ANDROID_WWW / name)
        icons = WEB / "icons"
        if icons.exists():
            shutil.copytree(icons, ANDROID_WWW / "icons", dirs_exist_ok=True)
        art = WEB / "art"
        if art.exists():
            shutil.copytree(art, ANDROID_WWW / "art", dirs_exist_ok=True)
        print(f"copied web assets to {ANDROID_WWW}")


if __name__ == "__main__":
    main()
