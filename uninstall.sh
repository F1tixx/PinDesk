#!/usr/bin/env bash
# Remove only PinDesk's own application-menu entry. Launchers you created with
# PinDesk are left untouched; delete those from the Manage tab first if wanted.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HERE="$HERE" python3 - <<'PY'
import os
import sys
from pathlib import Path

here = Path(os.environ["HERE"])
sys.path.insert(0, str(here))
import pindesk as pl

pl.migrate_legacy_config()
paths = pl.Paths(Path.home())
owned_ids = {"pindesk", "portable-launcher-maker"}
records = [r for r in pl.load_registry(paths) if r.get("id") in owned_ids]
if not records:
    # Older installs never wrote a registry entry; clean up by filename.
    records = [
        {"id": name.split(".")[0], "desktop_name": name}
        for name in ("pindesk.desktop", "portable-launcher-maker.desktop")
    ]
removed = []
for record in records:
    removed += pl.delete_launcher_files(record, paths)
    pl.remove_record(record["id"], paths)
print("Removed PinDesk menu entry." if removed else "PinDesk menu entry was not installed.")
PY
