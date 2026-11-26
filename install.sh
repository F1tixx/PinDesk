#!/usr/bin/env bash
# Optional: add PinDesk itself to the application menu.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "$HERE/pindesk.py"

HERE="$HERE" python3 - <<'PY'
import os
import sys
from pathlib import Path

here = Path(os.environ["HERE"])
sys.path.insert(0, str(here))
import pindesk as pl

pl.migrate_legacy_config()
script = here / "pindesk.py"
icon = pl.fallback_icon("PinDesk")
record = {
    "id": "pindesk",
    "desktop_name": "pindesk.desktop",
    "name": "PinDesk",
    "comment": "Create desktop launchers for portable apps",
    "exec_path": sys.executable,
    "extra_args": pl.quote_exec_arg(str(script)),
    "try_exec": sys.executable,
    "source_root": str(here),
    "workdir": str(here),
    "icon": icon,
    "categories": ["Utility"],
    "terminal": False,
    "startup_notify": True,
    "desktop_shortcut": False,
}
ok, message, warnings = pl.write_launcher(record)
if ok:
    pl.upsert_record(record)
print(message)
for warning in warnings:
    print("Note:", warning)
sys.exit(0 if ok else 1)
PY
