# How PinDesk works

PinDesk is one Python file. It uses `tkinter` for the UI and the Python standard
library for everything else. Pillow is optional and only improves icon scaling.

## Detection

`executable_candidates()` scans the chosen folder (and `bin/`) for executable
files. It skips:

- shared libraries (`*.so`, `*.a`, `*.o`, `*.dll`, …)
- docs and data files (`*.txt`, `*.md`, `*.json`, `*.png`, …)
- known helpers such as `uninstall`, `updater`, `xdg-open`

Each remaining candidate gets a score. Lower is better. Bonuses go to text
scripts, names that match the folder or icon names, `run`/`start`/`launch`
names, AppImages and extensionless files. Penalties go to nested binaries and
setup/helper names. This is why a wrapper script wins over the ELF binary under
`bin/`.

## Icons

`find_icon()` looks only in local places:

1. the app folder and its `icons/`, `share/icons/`, `assets/` and `meta/` directories
2. image filenames referenced inside a text launch script
3. installed icon themes via `find_theme_icon()`
4. a generated SVG with the app's initials via `fallback_icon()`

Candidates are ranked by filenames (`icon`, `logo`, app name), square dimensions,
image resolution and shallow location. No network lookups are ever made.

## Desktop Entry generation

`build_desktop()` writes a spec-compliant `[Desktop Entry]` group:

- `Type=Application`, `Version=1.5`, `Name=`, `Comment=`
- `Exec=` — the executable and arguments, each argument quoted with
  `quote_exec_arg()` (literal `%` doubled as `%%`)
- `Icon=` — an absolute path
- `Path=` — the working directory, so portable mode works
- `TryExec=` — lets menus hide entries whose target disappeared
- `Terminal=`, `StartupNotify=`, `Categories=`

String values go through `escape_field()` for `;`, `\`, newlines and tabs.
`validate_desktop_text()` runs `desktop-file-validate` if installed.

Files are written atomically: a temporary file in the same directory is fsynced
and renamed into place, so an interrupted write cannot leave a half-written
launcher.

## Registry and migration

PinDesk keeps a small JSON registry at `~/.config/pindesk/launchers.json`. It
records what PinDesk created so the Manage tab can list, edit and relocate those
launchers. `install.sh` registers PinDesk itself there too.

On first run after upgrading, `migrate_legacy_config()` moves the old
`~/.config/portable-launcher/` directory to the new location, preserving
existing entries.
