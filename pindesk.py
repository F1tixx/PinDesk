#!/usr/bin/env python3
"""PinDesk.

A small, dependency-free GUI for creating and managing .desktop launchers for
portable Linux apps (an executable/binary, a launch script or an AppImage).

It never runs the selected program. It only reads files and writes .desktop
files into the user's own XDG directories.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Iterable, Optional

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

APP_NAME = "PinDesk"
APP_VERSION = "1.0.1"
SCHEMA_VERSION = 1
MODULE_DIR = Path(__file__).resolve().parent
APP_ICON = MODULE_DIR / "docs" / "logo.png"
APP_LOGO_SVG = MODULE_DIR / "docs" / "logo.svg"

CATEGORIES = [
    "AudioVideo", "Audio", "Video", "Development", "Education", "Game",
    "Graphics", "Network", "Office", "Science", "Settings", "System", "Utility",
]

IMAGE_EXTENSIONS = {".png", ".svg", ".ico", ".xpm", ".jpg", ".jpeg", ".webp", ".bmp"}
SKIP_DIRS = {
    "cache", "logs", "log", "instances", "temp", "tmp", "java", "translations",
    "iconthemes", "node_modules", ".git", "__pycache__", "metacache",
}
SKIP_NAMES = {
    "sharun", "uninstall", "uninstaller", "updater", "update", "README", "LICENSE",
    "xdg-open", "gio-launch-desktop", "xdg-mime", "xdg-settings", "gsettings",
}
DROP_NAME_WORDS = {
    "linux", "portable", "appimage", "bin", "src", "x86", "x64", "x86_64",
    "win32", "win64", "aarch64", "arm64", "qt5", "qt6", "qt7",
}
EXEC_RESERVED = set(' \t\n"\'\\><|&;$*?#()~`')


# --------------------------------------------------------------------------- #
# Paths / registry
# --------------------------------------------------------------------------- #

@dataclass
class Paths:
    home: Path

    def config_dir(self) -> Path:
        return self.home / ".config" / "pindesk"

    def registry_file(self) -> Path:
        return self.config_dir() / "launchers.json"

    def icon_dir(self) -> Path:
        return self.config_dir() / "icons"

    def applications_dir(self) -> Path:
        return self.home / ".local" / "share" / "applications"

    def desktop_dir(self) -> Path:
        preferred = self.home / "Desktop"
        if preferred.is_dir():
            return preferred
        try:
            env = dict(os.environ, HOME=str(self.home))
            result = subprocess.run(
                ["xdg-user-dir", "DESKTOP"], env=env, capture_output=True,
                text=True, timeout=5,
            )
            value = result.stdout.strip()
            if value and Path(value).is_dir():
                return Path(value)
        except (OSError, subprocess.SubprocessError):
            pass
        return preferred


PATHS = Paths(Path.home())
LEGACY_CONFIG_DIR_NAME = "portable-launcher"


def migrate_legacy_config(paths: Paths = PATHS) -> bool:
    """Move settings from the pre-1.0 folder name; keep existing launchers listed."""
    legacy = paths.home / ".config" / LEGACY_CONFIG_DIR_NAME
    current = paths.config_dir()
    if current.exists() or not legacy.exists():
        return False
    try:
        current.parent.mkdir(parents=True, exist_ok=True)
        legacy.replace(current)
    except OSError:
        return False
    return True


def app_icon_path() -> Optional[str]:
    """Return PinDesk's own logo for the window and its menu entry, if present."""
    return str(APP_ICON) if APP_ICON.is_file() else None


def _temp_dir() -> Path:
    preferred = Path("/tmp/opencode")
    return preferred if preferred.is_dir() else Path(tempfile.gettempdir())


# Single, fixed dark theme. Rectangular widgets: no theme switching and no
# image-based styling, so colours cannot get out of sync with the text.
THEME = {
    "bg": "#181a1f", "surface": "#23262d", "field": "#2b2f38", "border": "#3a3f4a",
    "fg": "#e8eaf0", "muted": "#9aa2b1", "accent": "#5b9cf6", "hover": "#2f353f",
    "select": "#264f78",
}


def _dialog_result(command: list[str]) -> tuple[str, str]:
    """Run a native file dialog; return (ok|cancel|error, path-or-message)."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        return "error", str(exc)
    value = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")
    if result.returncode == 0 and value:
        return "ok", value
    if not value and result.returncode in (0, 1, 2):
        return "cancel", ""
    return "error", (result.stderr or result.stdout).strip()


def choose_folder(title: str, initial: str = "") -> str:
    """Prefer the desktop environment's own folder chooser (kdialog on KDE)."""
    start = str(Path(initial).expanduser()) if initial else str(Path.home())
    if not Path(start).is_dir():
        start = str(Path.home())

    if shutil.which("kdialog"):
        status, value = _dialog_result(["kdialog", "--title", title, "--getexistingdirectory", start])
        if status == "ok" and Path(value).is_dir():
            return value
        if status == "cancel":
            return ""
    if shutil.which("zenity"):
        command = ["zenity", "--file-selection", "--directory", "--title", title]
        if Path(start).is_dir():
            command += ["--filename", start.rstrip("/") + "/"]
        status, value = _dialog_result(command)
        if status == "ok" and Path(value).is_dir():
            return value
        if status == "cancel":
            return ""
    if shutil.which("yad"):
        command = ["yad", "--file-selection", "--directory", "--title", title]
        status, value = _dialog_result(command)
        if status == "ok" and Path(value).is_dir():
            return value
        if status == "cancel":
            return ""
    return filedialog.askdirectory(title=title, initialdir=start)


def choose_file(title: str, initial: str = "", images_only: bool = False) -> str:
    """Prefer a native file chooser, falling back to Tk's dialog."""
    image_pattern = "*.png *.svg *.ico *.xpm *.jpg *.jpeg *.webp"
    start = str(Path(initial).expanduser()) if initial else str(Path.home())
    if not Path(start).is_dir():
        start = str(Path.home())

    if shutil.which("kdialog"):
        command = ["kdialog", "--title", title, "--getopenfilename", start]
        if images_only:
            command.append("Images (" + image_pattern + ")")
        status, value = _dialog_result(command)
        if status == "ok" and Path(value).is_file():
            return value
        if status == "cancel":
            return ""
    if shutil.which("zenity"):
        command = ["zenity", "--file-selection", "--title", title]
        if images_only:
            command.append("--file-filter=Images | " + image_pattern)
        status, value = _dialog_result(command)
        if status == "ok" and Path(value).is_file():
            return value
        if status == "cancel":
            return ""
    if images_only:
        return filedialog.askopenfilename(
            title=title, initialdir=start, filetypes=[("Images", image_pattern.split())])
    return filedialog.askopenfilename(title=title, initialdir=start)


def _atomic_write(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".pindesk-", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def load_registry(paths: Paths = PATHS) -> list[dict]:
    try:
        with paths.registry_file().open(encoding="utf-8") as handle:
            data = json.load(handle)
        records = data.get("launchers", [])
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]
    except (OSError, ValueError, TypeError):
        pass
    return []


def save_registry(records: Iterable[dict], paths: Paths = PATHS) -> None:
    payload = {"schema": SCHEMA_VERSION, "launchers": list(records)}
    _atomic_write(paths.registry_file(), json.dumps(payload, indent=2, ensure_ascii=False) + "\n", 0o600)


def upsert_record(record: dict, paths: Paths = PATHS) -> list[dict]:
    records = load_registry(paths)
    replaced = False
    for index, existing in enumerate(records):
        if existing.get("id") == record.get("id"):
            records[index] = record
            replaced = True
            break
    if not replaced:
        records.append(record)
    save_registry(records, paths)
    return records


def remove_record(record_id: str, paths: Paths = PATHS) -> list[dict]:
    records = [item for item in load_registry(paths) if item.get("id") != record_id]
    save_registry(records, paths)
    return records


# --------------------------------------------------------------------------- #
# Desktop Entry generation
# --------------------------------------------------------------------------- #

def escape_field(value: str) -> str:
    """Escape a string/localestring value according to the Desktop Entry spec."""
    return (str(value)
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
            .replace("\r", "\\r"))


def quote_exec_arg(value: str) -> str:
    """Quote one Exec argument; literal '%' becomes '%%' (field-code escaping)."""
    if value == "":
        return '""'
    percent_escaped = str(value).replace("%", "%%")
    if not any(char in EXEC_RESERVED for char in value):
        return percent_escaped
    quoted = (percent_escaped
              .replace("\\", "\\\\\\\\")
              .replace('"', '\\"')
              .replace("$", "\\\\$")
              .replace("`", "\\`"))
    return '"' + quoted + '"'


def build_desktop(record: dict) -> str:
    """Render a record as a valid .desktop file."""
    for key in ("name", "comment", "exec_path", "extra_args"):
        value = str(record.get(key, ""))
        if any(ch in value for ch in ("\n", "\r", "\0")):
            raise ValueError(f"{key} must not contain newlines")

    command = quote_exec_arg(record["exec_path"])
    extra_args = str(record.get("extra_args", "")).strip()
    if extra_args:
        command += " " + extra_args

    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.5",
        "Name=" + escape_field(record["name"]),
        "Comment=" + escape_field(record.get("comment", "")),
        "Exec=" + command,
    ]
    icon = str(record.get("icon", "")).strip()
    if icon:
        lines.append("Icon=" + escape_field(icon))
    workdir = str(record.get("workdir", "")).strip()
    if workdir:
        lines.append("Path=" + escape_field(workdir))
    lines.extend([
        "TryExec=" + quote_exec_arg(record.get("try_exec") or record["exec_path"]),
        "Terminal=" + ("true" if record.get("terminal") else "false"),
        "StartupNotify=" + ("true" if record.get("startup_notify", True) else "false"),
        "Categories=" + ";".join(record.get("categories", [])) + ";",
    ])
    if record.get("wm_class"):
        lines.append("StartupWMClass=" + escape_field(record["wm_class"]))
    lines.append("X-PortableLauncher-Id=" + escape_field(record["id"]))
    if record.get("source_root"):
        lines.append("X-PortableLauncher-Root=" + escape_field(record["source_root"]))
    return "\n".join(lines) + "\n"


def validate_desktop_text(text: str) -> tuple[bool, str]:
    """Return (is_valid, validator_output). Missing validator is not an error."""
    executable = shutil.which("desktop-file-validate")
    if not executable:
        return True, "desktop-file-validate not installed; skipped validation"
    with tempfile.NamedTemporaryFile(
        "w", suffix=".desktop", dir=str(_temp_dir()), delete=False, encoding="utf-8"
    ) as handle:
        handle.write(text)
        path = Path(handle.name)
    try:
        result = subprocess.run([executable, str(path)], capture_output=True, text=True, timeout=20)
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except (OSError, subprocess.SubprocessError) as exc:
        return True, f"validation skipped: {exc}"
    finally:
        path.unlink(missing_ok=True)


def trust_desktop_file(path: Path) -> tuple[bool, str]:
    """Best-effort GNOME-style trust flag. KDE/XFCE may use other mechanisms."""
    gio = shutil.which("gio")
    if not gio:
        return False, "gio not installed"
    for value in ("true", "yes"):
        try:
            result = subprocess.run(
                [gio, "set", str(path), "metadata::trusted", value],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return True, ""
            message = (result.stderr or result.stdout).strip()
        except (OSError, subprocess.SubprocessError) as exc:
            message = str(exc)
    return False, message


def refresh_desktop_database(paths: Paths = PATHS) -> None:
    tool = shutil.which("update-desktop-database")
    if not tool:
        return
    try:
        subprocess.run([tool, str(paths.applications_dir())],
                       capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass


def write_launcher(record: dict, paths: Paths = PATHS) -> tuple[bool, str, list[str]]:
    """Validate, write the .desktop file, optionally place a desktop shortcut."""
    warnings: list[str] = []
    try:
        text = build_desktop(record)
    except (ValueError, KeyError) as exc:
        return False, f"Cannot build launcher: {exc}", warnings

    valid, output = validate_desktop_text(text)
    if not valid:
        return False, "Invalid desktop entry:\n" + (output or "unknown validation error"), warnings

    _atomic_write(paths.applications_dir() / record["desktop_name"], text)

    if record.get("desktop_shortcut"):
        desktop_file = paths.desktop_dir() / record["desktop_name"]
        try:
            _atomic_write(desktop_file, text, 0o755)
        except OSError as exc:
            warnings.append(f"Could not place shortcut on Desktop: {exc}")
        else:
            trusted, message = trust_desktop_file(desktop_file)
            if not trusted:
                warnings.append(
                    "Shortcut was created, but this desktop environment did not accept the "
                    "trust flag. If it refuses to launch, right-click it and choose "
                    "'Allow Launching'. " + message
                )

    refresh_desktop_database(paths)
    return True, f"Created {record['desktop_name']}", warnings


def delete_launcher_files(record: dict, paths: Paths = PATHS) -> list[str]:
    removed = []
    for directory in (paths.applications_dir(), paths.desktop_dir()):
        candidate = directory / record["desktop_name"]
        try:
            if candidate.exists():
                candidate.unlink()
                removed.append(str(candidate))
        except OSError:
            pass
    refresh_desktop_database(paths)
    return removed


# --------------------------------------------------------------------------- #
# Detection helpers
# --------------------------------------------------------------------------- #

def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug or "app"


def guess_name(folder: Path) -> str:
    raw = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", folder.name)
    parts = re.split(r"[\s_\-.]+", raw)
    kept = []
    for part in parts:
        low = part.lower()
        if not low or low in DROP_NAME_WORDS:
            continue
        if re.fullmatch(r"v?\d+(?:[.\-_]\d+)*[a-z]?", low):
            continue
        if re.fullmatch(r"qt\d+", low):
            continue
        kept.append(part[:1].upper() + part[1:])
    return " ".join(kept) if kept else folder.name.replace("_", " ")


def is_text_script(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


def choose_root(executable: Path) -> Path:
    root = executable.parent
    if root.name.lower() in {"bin", "scripts", "sbin"}:
        parent = root.parent
        if any((parent / marker).exists() for marker in ("portable.txt", "AppRun", ".DirIcon")):
            return parent
        return parent
    return root


def _is_library(path: Path) -> bool:
    """Shared libraries often carry the executable bit; they are not launchers."""
    name = path.name.lower()
    if re.search(r"\.so(?:\.\d+)*$", name):
        return True
    return name.endswith((".a", ".o", ".dll", ".dylib", ".pyd", ".pyc"))


def _name_hints(root: Path) -> set[str]:
    """Derive likely app-name tokens from the folder and icon filenames."""
    hints = {token for token in re.split(r"[^a-z0-9]+", slugify(root.name)) if len(token) > 1}
    try:
        for entry in os.scandir(root):
            if entry.is_file() and Path(entry.name).suffix.lower() in IMAGE_EXTENSIONS:
                for token in re.split(r"[^a-z0-9]+", slugify(Path(entry.name).stem)):
                    if len(token) > 1 and token not in {"icon", "logo", "png", "svg"}:
                        hints.add(token)
    except OSError:
        pass
    return hints


def _exec_score(path: Path, root: Path, hints: set[str]) -> tuple[float, str]:
    """Lower is better. Scripts and names matching the app are preferred."""
    score = 0.0
    if path.parent != root:
        score += 12
    if is_text_script(path):
        score -= 50
    stem = path.stem.lower()
    slug = slugify(stem)
    if slug in hints:
        score -= 40
    elif any(hint == slug or (len(hint) > 2 and hint in slug) or (len(slug) > 2 and slug in hint)
             for hint in hints):
        score -= 25
    if stem in {"apprun", "start", "launch", "run", "main"}:
        score -= 30
    if path.suffix.lower() == ".appimage":
        score -= 15
    if not path.suffix:
        score -= 5
    if any(word in path.name.lower() for word in ("updater", "uninstall", "setup", "helper")):
        score += 40
    score += min(len(stem), 24) / 24
    return score, path.name.lower()


def executable_candidates(root: Path) -> list[Path]:
    """Find likely launch targets, excluding shared libraries and helpers."""
    found: list[Path] = []
    folders = [root]
    sub = root / "bin"
    if sub.is_dir():
        folders.append(sub)
    hints = _name_hints(root)

    for folder in folders:
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            if not entry.is_file(follow_symlinks=True):
                continue
            path = Path(entry.path)
            low = path.name.lower()
            if path.suffix.lower() in {".desktop", ".txt", ".md", ".json", ".png", ".svg", ".pak"}:
                continue
            if low in SKIP_NAMES or _is_library(path):
                continue
            if not os.access(path, os.X_OK):
                continue
            try:
                if path.stat().st_size == 0:
                    continue
            except OSError:
                continue
            found.append(path)

    return sorted(found, key=lambda p: _exec_score(p, root, hints))


def _image_size(path: Path) -> tuple[int, int]:
    try:
        suffix = path.suffix.lower()
        if suffix == ".png":
            with path.open("rb") as handle:
                header = handle.read(24)
            if header[:8] == b"\x89PNG\r\n\x1a\n" and len(header) >= 24:
                return struct.unpack(">II", header[16:24])
        if suffix == ".svg":
            text = path.read_text(encoding="utf-8", errors="ignore")[:4096]
            match = re.search(r'width\s*=\s*["\'](\d+)', text)
            height = re.search(r'height\s*=\s*["\'](\d+)', text)
            if match and height:
                return int(match.group(1)), int(height.group(2))
            viewbox = re.search(r'viewBox\s*=\s*["\'][\d.\-]+\s+[\d.\-]+\s+(\d+)[.\d]*\s+(\d+)', text)
            if viewbox:
                return int(float(viewbox.group(1))), int(float(viewbox.group(2)))
        if suffix == ".ico":
            with path.open("rb") as handle:
                header = handle.read(8)
            if len(header) == 8:
                width, height = header[6] or 256, header[7] or 256
                return width, height
    except (OSError, ValueError, struct.error):
        pass
    return 0, 0


def _icon_rank(path: Path, root: Path, app_name: str) -> tuple[int, int, int, int]:
    width, height = _image_size(path)
    stem = path.stem.lower()
    name_words = {word.lower() for word in re.split(r"[^a-z0-9]+", app_name) if word}
    bonus = 0
    if stem in {"icon", "logo", "app", "application", "diricon", ".diricon"}:
        bonus += 100
    if stem in name_words or slugify(app_name) in slugify(stem):
        bonus += 60
    if any(token in stem for token in ("icon", "logo")):
        bonus += 20
    if path.suffix.lower() in {".png", ".svg"}:
        bonus += 10
    try:
        depth = len(path.relative_to(root).parts)
    except ValueError:
        depth = 9
    bonus -= depth * 8
    square_bonus = 40 if width and width == height else 0
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return (-bonus, -square_bonus, -(min(width, height) if width else 1), -size)


def find_icon(root: Path, executable: Optional[Path] = None, app_name: str = "") -> Optional[str]:
    """Search local files only: app folder, icon folders, and script references."""
    candidates: set[Path] = set()
    for folder in (root, root / "icons", root / "share" / "icons", root / "assets", root / "meta"):
        if not folder.is_dir():
            continue
        try:
            for entry in os.scandir(folder):
                if entry.name.lower() in SKIP_DIRS:
                    continue
                if entry.is_file() and Path(entry.name).suffix.lower() in IMAGE_EXTENSIONS:
                    candidates.add(Path(entry.path))
        except OSError:
            continue

    if executable and is_text_script(executable):
        try:
            text = executable.read_text(encoding="utf-8", errors="ignore")[:65536]
            for token in re.findall(r"[^\s\"'()]+?\.(?:png|svg|ico|xpm|jpg|jpeg|webp)", text, re.I):
                reference = Path(token)
                if not reference.is_absolute():
                    reference = (executable.parent / reference).resolve()
                if reference.is_file():
                    candidates.add(reference)
        except OSError:
            pass

    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda p: _icon_rank(p, root, app_name))
    return str(ranked[0].resolve())


def find_theme_icon(app_name: str, paths: Paths = PATHS) -> Optional[str]:
    names = [slugify(app_name), slugify(app_name).replace("-", ""), app_name.lower()]
    roots = [
        paths.home / ".local" / "share" / "icons",
        Path("/usr/share/icons"),
        Path("/usr/share/pixmaps"),
    ]
    for theme_root in roots:
        if not theme_root.is_dir():
            continue
        for name in names:
            for suffix in (".png", ".svg", ".xpm"):
                direct = theme_root / (name + suffix)
                if direct.is_file():
                    return str(direct)
            if theme_root.name == "icons":
                try:
                    for theme in os.scandir(theme_root):
                        if not theme.is_dir():
                            continue
                        for size in ("128x128", "64x64", "48x48", "scalable"):
                            for suffix in (".png", ".svg"):
                                candidate = Path(theme.path) / size / "apps" / (name + suffix)
                                if candidate.is_file():
                                    return str(candidate)
                except OSError:
                    continue
    return None


def fallback_icon(app_name: str, paths: Paths = PATHS) -> str:
    """Generate a simple SVG icon with initials; no external dependencies."""
    words = [word for word in re.split(r"[^A-Za-z0-9]+", app_name) if word]
    initials = "".join(word[0] for word in words[:2]).upper() or "?"
    initials = initials.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    digest = hashlib.sha256(app_name.encode("utf-8")).digest()
    color = f"#{digest[0]:02x}{digest[1]:02x}{digest[2]:02x}"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">'
        f'<rect x="4" y="4" width="120" height="120" rx="26" fill="{color}"/>'
        '<text x="64" y="64" fill="white" font-family="sans-serif" font-size="52" '
        'font-weight="bold" text-anchor="middle" dominant-baseline="central">'
        f'{initials}</text></svg>\n'
    )
    icon_path = paths.icon_dir() / f"{slugify(app_name)}.svg"
    _atomic_write(icon_path, svg)
    return str(icon_path)


def detect_fields(source: Path, paths: Paths = PATHS) -> dict:
    """Fill in record fields from a chosen executable or folder."""
    source = source.resolve()
    if source.is_dir():
        root = source
        candidates = executable_candidates(root)
        executable = candidates[0] if candidates else None
        name = guess_name(root)
    else:
        executable = source
        root = choose_root(source)
        looks_like_app_root = any(
            (root / marker).exists() for marker in ("portable.txt", "AppRun", ".DirIcon")
        )
        name = guess_name(root) if looks_like_app_root else guess_name(Path(executable.stem or executable.name))

    icon = (find_icon(root, executable, name)
            or find_theme_icon(name, paths)
            or fallback_icon(name, paths))
    return {
        "name": name,
        "comment": f"Portable app in {root.name}",
        "source_root": str(root),
        "exec_candidates": [str(item) for item in (candidates if source.is_dir() else [source])[:8]],
        "exec_path": str(executable) if executable else "",
        "try_exec": str(executable) if executable else "",
        "workdir": str(root),
        "icon": icon,
        "categories": ["Game"],
        "terminal": False,
        "startup_notify": True,
        "desktop_shortcut": True,
        "extra_args": "",
    }


def new_record_id(name: str, exec_path: str, existing: Iterable[dict]) -> str:
    base = slugify(name)
    taken = {item.get("id") for item in existing}
    if base not in taken:
        return base
    digest = hashlib.sha1(exec_path.encode("utf-8")).hexdigest()[:6]
    candidate = f"{base}-{digest}"
    counter = 2
    while candidate in taken:
        candidate = f"{base}-{digest}-{counter}"
        counter += 1
    return candidate


def desktop_name_for(record_id: str, existing: Iterable[dict]) -> str:
    base = slugify(record_id)
    taken = {item.get("desktop_name") for item in existing if item.get("id") != record_id}
    name = f"{base}.desktop"
    counter = 2
    while name in taken:
        name = f"{base}-{counter}.desktop"
        counter += 1
    return name


def relocate_record(record: dict, old_root: str, new_root: str) -> dict:
    """Rewrite all absolute paths that point inside old_root."""
    updated = dict(record)
    old_root = str(old_root).rstrip("/")
    new_root = str(new_root).rstrip("/")
    for key in ("exec_path", "try_exec", "workdir", "icon", "source_root"):
        value = str(updated.get(key, ""))
        if value == old_root:
            updated[key] = new_root
        elif value.startswith(old_root + "/"):
            updated[key] = new_root + value[len(old_root):]
    if updated.get("source_root"):
        updated["comment"] = f"Portable app in {Path(updated['source_root']).name}"
    return updated


def find_root_candidates(root_name: str) -> list[Path]:
    bases = [Path("/mnt"), Path("/media"), Path("/run/media")]
    home_media = Path.home() / "mnt"
    if home_media.is_dir():
        bases.append(home_media)
    found: list[Path] = []
    for base in bases:
        if not base.is_dir():
            continue
        try:
            for first in os.scandir(base):
                if not first.is_dir():
                    continue
                direct = Path(first.path) / root_name
                if direct.is_dir():
                    found.append(direct)
                try:
                    for second in os.scandir(first.path):
                        candidate = Path(second.path) / root_name
                        if second.is_dir() and candidate.is_dir():
                            found.append(candidate)
                except OSError:
                    continue
        except OSError:
            continue
    return sorted(set(found))


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #

class LauncherApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.icon_image: Optional[tk.PhotoImage] = None
        icon = app_icon_path()
        if icon:
            try:
                self.icon_image = tk.PhotoImage(file=icon)
                self.iconphoto(True, self.icon_image)
            except (tk.TclError, OSError):
                self.icon_image = None
        self.geometry("860x780")
        self.minsize(760, 680)
        self.paths = PATHS
        self.records = load_registry(self.paths)
        self.current_id: Optional[str] = None
        self._icon_images: dict[str, tk.PhotoImage] = {}
        self.vars: dict[str, tk.Variable] = {}
        self._build_ui()
        self._refresh_list()

    # -- UI construction ---------------------------------------------------- #

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=(14, 10, 14, 6))
        top.pack(side="top", fill="x")
        ttk.Label(top, text=APP_NAME, style="Header.TLabel").pack(side="left")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.notebook = notebook
        create = ttk.Frame(notebook, padding=14)
        manage = ttk.Frame(notebook, padding=14)
        notebook.add(create, text="Create launcher")
        notebook.add(manage, text="Manage")
        self._build_create_tab(create)
        self._build_manage_tab(manage)
        self.apply_current_theme()

    def _build_create_tab(self, parent: ttk.Frame) -> None:
        self.vars = {
            "source": tk.StringVar(), "executable": tk.StringVar(),
            "make_executable": tk.BooleanVar(value=True),
            "name": tk.StringVar(), "comment": tk.StringVar(), "icon": tk.StringVar(),
            "workdir": tk.StringVar(), "category": tk.StringVar(value="Game"),
            "args": tk.StringVar(), "terminal": tk.BooleanVar(value=False),
            "startup_notify": tk.BooleanVar(value=True),
            "desktop_shortcut": tk.BooleanVar(value=True),
        }

        actions = ttk.Frame(parent)
        actions.pack(side="bottom", fill="x", pady=(10, 0))
        self.actions = actions
        self.add_button = ttk.Button(actions, text="Add launcher", style="Accent.TButton",
                                     command=self._save)
        self.add_button.pack(side="left")
        ttk.Button(actions, text="New", command=self._reset).pack(side="left", padx=(8, 0))
        self.delete_button = ttk.Button(actions, text="Delete", command=self._delete)
        self.delete_button.pack(side="left", padx=(8, 0))
        self.delete_button.configure(state="disabled")
        ttk.Label(actions, text="Saves to ~/.local/share/applications",
                  style="Muted.TLabel").pack(side="right")
        ttk.Button(actions, text="Open folder", command=self._open_folder).pack(side="right", padx=(0, 12))

        self.preview_frame = ttk.LabelFrame(parent, text="Generated .desktop", padding=8)
        self.preview = tk.Text(self.preview_frame, height=8, wrap="none", font="TkFixedFont",
                               bd=0, highlightthickness=1)
        scrollbar = ttk.Scrollbar(self.preview_frame, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=scrollbar.set, state="disabled")
        self.preview.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.preview_visible = False

        form = ttk.Frame(parent)
        form.pack(side="top", fill="x")

        self._grid_row(form, "App folder", ttk.Entry(form, textvariable=self.vars["source"], width=58), 0,
                       [("Browse", self._browse_folder), ("Auto-detect", self._detect)])
        self.exec_combo = ttk.Combobox(form, textvariable=self.vars["executable"], width=56)
        self._grid_row(form, "Launcher file", self.exec_combo, 1,
                       [("Browse", self._browse_executable)])
        self._grid_row(form, "Name", ttk.Entry(form, textvariable=self.vars["name"], width=58), 2)
        self._grid_row(form, "Icon", ttk.Entry(form, textvariable=self.vars["icon"], width=58), 3,
                       [("Browse", self._browse_icon), ("Find icon", self._detect_icon)])

        ttk.Label(form, text="Category").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Combobox(form, textvariable=self.vars["category"], values=CATEGORIES,
                     width=18).grid(row=4, column=1, sticky="w", pady=3)
        ttk.Checkbutton(form, text="Desktop shortcut",
                        variable=self.vars["desktop_shortcut"]).grid(row=4, column=2, sticky="w", padx=(10, 0))

        self.more_button = ttk.Button(form, text="More options", command=self._toggle_advanced)
        self.more_button.grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.preview_button = ttk.Button(form, text="Show .desktop preview", command=self._toggle_preview)
        self.preview_button.grid(row=5, column=1, sticky="w", padx=(10, 0), pady=(8, 0))

        self.advanced = ttk.Frame(form)
        self.advanced.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self._grid_row(self.advanced, "Comment",
                       ttk.Entry(self.advanced, textvariable=self.vars["comment"], width=58), 0)
        self._grid_row(self.advanced, "Working dir",
                       ttk.Entry(self.advanced, textvariable=self.vars["workdir"], width=58), 1,
                       [("Browse", self._browse_workdir)])
        self._grid_row(self.advanced, "Extra args",
                       ttk.Entry(self.advanced, textvariable=self.vars["args"], width=58), 2)
        ttk.Label(self.advanced, text="Use %u for a dropped file, %% for a literal percent.",
                  style="Muted.TLabel").grid(row=3, column=1, sticky="w")
        ttk.Checkbutton(self.advanced, text="Run in terminal",
                        variable=self.vars["terminal"]).grid(row=4, column=1, sticky="w", pady=(4, 0))
        ttk.Checkbutton(self.advanced, text="Make launcher file executable if needed",
                        variable=self.vars["make_executable"]).grid(row=4, column=2, sticky="w", padx=(10, 0))
        self.advanced.grid_remove()
        self.advanced_visible = False

        for variable in self.vars.values():
            variable.trace_add("write", lambda *_: self._update_preview())
        self._update_preview()

    def _build_manage_tab(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x")
        ttk.Label(top, text="Launchers created with this tool").pack(side="left")
        ttk.Button(top, text="Refresh", command=self._refresh_list).pack(side="right")

        self.tree = ttk.Treeview(parent, columns=("name", "target", "root"),
                                 show="tree headings", height=14)
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=34, stretch=False, anchor="center")
        for key, label, width in (("name", "Name", 200), ("target", "Launcher file", 170),
                                  ("root", "App folder", 390)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=(10, 0))
        self.tree.bind("<Double-1>", lambda *_: self._edit_selected())

        buttons = ttk.Frame(parent)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Edit selected", command=self._edit_selected).pack(side="left")
        ttk.Button(buttons, text="Remove selected", command=self._remove_selected).pack(side="left", padx=8)
        ttk.Button(buttons, text="Fix moved app folders...", command=self._fix_paths).pack(side="left", padx=8)

        status = ttk.LabelFrame(parent, text="Status", padding=8)
        status.pack(fill="x", pady=(10, 0))
        self.status = tk.Text(status, height=5, wrap="word", bd=0, highlightthickness=0)
        self.status.pack(fill="x")

    def _grid_row(self, parent: ttk.Frame, label: str, widget: tk.Widget, row: int,
                  buttons: Iterable[tuple[str, object]] = ()) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
        widget.grid(row=row, column=1, sticky="ew", pady=3)
        for index, (text, command) in enumerate(buttons):
            ttk.Button(parent, text=text, command=command).grid(
                row=row, column=2 + index, sticky="w", padx=(6, 0), pady=3)
        parent.columnconfigure(1, weight=1)

    def _toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced.grid()
            self.more_button.configure(text="Fewer options")
        else:
            self.advanced.grid_remove()
            self.more_button.configure(text="More options")

    def _toggle_preview(self) -> None:
        self.preview_visible = not self.preview_visible
        if self.preview_visible:
            self.preview_frame.pack(side="bottom", fill="both", expand=True,
                                    before=self.actions, pady=(8, 0))
            self.preview_button.configure(text="Hide .desktop preview")
        else:
            self.preview_frame.pack_forget()
            self.preview_button.configure(text="Show .desktop preview")

    def apply_current_theme(self) -> None:
        """Apply the single, fixed dark theme to all widgets."""
        c = THEME
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        def cfg(name: str, **kwargs) -> None:
            try:
                style.configure(name, **kwargs)
            except tk.TclError:
                pass

        def mp(name: str, **kwargs) -> None:
            try:
                style.map(name, **kwargs)
            except tk.TclError:
                pass

        cfg(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["field"],
            bordercolor=c["border"], troughcolor=c["surface"],
            selectbackground=c["select"], selectforeground=c["fg"], insertcolor=c["fg"])
        cfg("TFrame", background=c["bg"])
        cfg("TLabel", background=c["bg"], foreground=c["fg"], font=("TkDefaultFont", 10))
        cfg("Header.TLabel", background=c["bg"], foreground=c["accent"],
            font=("TkDefaultFont", 14, "bold"))
        cfg("Muted.TLabel", background=c["bg"], foreground=c["muted"],
            font=("TkDefaultFont", 9))
        cfg("TLabelframe", background=c["bg"], foreground=c["fg"], borderwidth=1,
            relief="groove", bordercolor=c["border"])
        cfg("TLabelframe.Label", background=c["bg"], foreground=c["accent"],
            font=("TkDefaultFont", 10, "bold"))
        cfg("TButton", background=c["surface"], foreground=c["fg"], borderwidth=1,
            relief="flat", bordercolor=c["border"], padding=(12, 7),
            font=("TkDefaultFont", 10))
        mp("TButton", background=[("active", c["hover"])], foreground=[("disabled", c["muted"])])
        cfg("Accent.TButton", background=c["accent"], foreground="#ffffff", borderwidth=1,
            relief="flat", bordercolor=c["accent"], padding=(18, 10),
            font=("TkDefaultFont", 11, "bold"))
        mp("Accent.TButton", background=[("active", c["accent"])],
           foreground=[("disabled", c["muted"])])
        cfg("TEntry", fieldbackground=c["field"], foreground=c["fg"], insertcolor=c["fg"],
            bordercolor=c["border"], borderwidth=1, relief="flat", padding=(8, 6))
        cfg("TCombobox", fieldbackground=c["field"], foreground=c["fg"], insertcolor=c["fg"],
            bordercolor=c["border"], borderwidth=1, relief="flat", padding=(7, 5))
        mp("TCombobox", fieldbackground=[("readonly", c["field"])])
        cfg("TCheckbutton", background=c["bg"], foreground=c["fg"], borderwidth=0,
            font=("TkDefaultFont", 10))
        mp("TCheckbutton", background=[("active", c["bg"])])
        cfg("Treeview", background=c["field"], fieldbackground=c["field"], foreground=c["fg"],
            bordercolor=c["border"], borderwidth=1, rowheight=30)
        cfg("Treeview.Heading", background=c["surface"], foreground=c["fg"],
            borderwidth=1, font=("TkDefaultFont", 10, "bold"))
        cfg("TScrollbar", background=c["surface"], troughcolor=c["bg"],
            bordercolor=c["border"], borderwidth=0, arrowcolor=c["fg"])
        cfg("TNotebook", background=c["bg"], bordercolor=c["border"], borderwidth=0)
        cfg("TNotebook.Tab", background=c["surface"], foreground=c["fg"], borderwidth=1,
            bordercolor=c["border"], padding=(16, 8))
        mp("TNotebook.Tab", background=[("selected", c["field"])],
           foreground=[("selected", c["accent"])])
        self.configure(bg=c["bg"])
        for widget in (self.preview, self.status):
            widget.configure(bg=c["field"], fg=c["fg"], insertbackground=c["fg"],
                             highlightbackground=c["border"], highlightthickness=1,
                             selectbackground=c["select"])


    def _log(self, message: str) -> None:
        self.status.configure(state="normal")
        self.status.insert("end", message.rstrip() + "\n")
        self.status.see("end")
        self.status.configure(state="disabled")

    # -- Actions ------------------------------------------------------------ #

    def _browse_folder(self) -> None:
        chosen = choose_folder("Select the portable app folder", self.vars["source"].get())
        if chosen:
            self.vars["source"].set(chosen)
            self._detect()

    def _browse_executable(self) -> None:
        chosen = choose_file("Select the launch script or executable",
                             self.vars["source"].get() or str(Path.home()))
        if chosen:
            self.vars["executable"].set(chosen)
            if not self.vars["source"].get():
                self.vars["source"].set(str(choose_root(Path(chosen))))

    def _browse_icon(self) -> None:
        chosen = choose_file("Select an icon", self.vars["source"].get()
                             or str(Path.home()), images_only=True)
        if chosen:
            self.vars["icon"].set(chosen)

    def _browse_workdir(self) -> None:
        chosen = choose_folder("Select the working directory", self.vars["workdir"].get())
        if chosen:
            self.vars["workdir"].set(chosen)

    def _detect_icon(self) -> None:
        raw = self.vars["source"].get().strip()
        if not raw:
            messagebox.showinfo(APP_NAME, "Choose the app folder first.")
            return
        root = Path(raw).expanduser()
        if not root.is_dir():
            root = root.parent
        icon = (find_icon(root, None, self.vars["name"].get())
                or find_theme_icon(self.vars["name"].get(), self.paths))
        if icon:
            self.vars["icon"].set(icon)
            self._log(f"Found icon: {icon}")
        else:
            self.vars["icon"].set(fallback_icon(self.vars["name"].get() or root.name, self.paths))
            self._log("No icon found; generated a fallback icon.")

    def _detect(self) -> None:
        raw = self.vars["source"].get().strip() or self.vars["executable"].get().strip()
        if not raw:
            messagebox.showinfo(APP_NAME, "Choose a folder or launcher file first.")
            return
        source = Path(raw).expanduser()
        if not source.exists():
            messagebox.showerror(APP_NAME, f"Not found: {source}")
            return
        detected = detect_fields(source, self.paths)
        candidates = detected.get("exec_candidates", [])
        if hasattr(self, "exec_combo"):
            self.exec_combo["values"] = candidates
        if not detected["exec_path"]:
            messagebox.showerror(APP_NAME, "No executable file was found in that folder. Select one manually.")
            return
        for key, value in detected.items():
            if key in self.vars:
                self.vars[key].set(value)
        self.vars["executable"].set(detected["exec_path"])
        self.vars["source"].set(detected["source_root"])
        self._update_preview()
        self._log(f"Detected {detected['name']}: {detected['exec_path']}")
        if len(candidates) > 1:
            self._log(f"Other launch targets available in the Launcher file dropdown ({len(candidates)} total).")

    def _record_from_form(self) -> dict:
        record = {
            "id": self.current_id or "",
            "name": self.vars["name"].get().strip(),
            "comment": self.vars["comment"].get().strip(),
            "source_root": self.vars["source"].get().strip(),
            "exec_path": self.vars["executable"].get().strip(),
            "try_exec": self.vars["executable"].get().strip(),
            "workdir": self.vars["workdir"].get().strip(),
            "icon": self.vars["icon"].get().strip(),
            "categories": [part.strip() for part in self.vars["category"].get().split(";") if part.strip()],
            "terminal": self.vars["terminal"].get(),
            "startup_notify": self.vars["startup_notify"].get(),
            "desktop_shortcut": self.vars["desktop_shortcut"].get(),
            "extra_args": self.vars["args"].get().strip(),
        }
        return record

    def _form_valid(self, record: dict) -> bool:
        for key in ("name", "exec_path"):
            if not record.get(key):
                messagebox.showerror(APP_NAME, f"Please fill in {key.replace('_', ' ')}.")
                return False
            if any(ch in record[key] for ch in ("\n", "\r", "\0")):
                messagebox.showerror(APP_NAME, f"{key} contains invalid characters.")
                return False
        executable = Path(record["exec_path"]).expanduser()
        if not executable.is_file():
            messagebox.showerror(APP_NAME, f"Launcher file does not exist:\n{executable}")
            return False
        if not os.access(executable, os.X_OK):
            if self.vars["make_executable"].get():
                try:
                    executable.chmod(executable.stat().st_mode | 0o111)
                except OSError as exc:
                    messagebox.showerror(APP_NAME, f"Could not make the file executable: {exc}")
                    return False
            else:
                messagebox.showerror(APP_NAME, "The selected launcher file is not executable.")
                return False
        return True

    def _save(self) -> None:
        record = self._record_from_form()
        if not self._form_valid(record):
            return
        existing = load_registry(self.paths)
        if self.current_id is None:
            record["id"] = new_record_id(record["name"], record["exec_path"], existing)
            record["desktop_name"] = desktop_name_for(record["id"], existing)
        else:
            record["id"] = self.current_id
            previous = next((item for item in existing if item.get("id") == self.current_id), {})
            record["desktop_name"] = previous.get("desktop_name") or desktop_name_for(self.current_id, existing)

        ok, message, warnings = write_launcher(record, self.paths)
        if not ok:
            messagebox.showerror(APP_NAME, message)
            return
        upsert_record(record, self.paths)
        self.records = load_registry(self.paths)
        self.current_id = record["id"]
        self.delete_button.configure(state="normal")
        self._refresh_list()
        self._log(message)
        for warning in warnings:
            self._log("Note: " + warning)
        if warnings:
            messagebox.showwarning(APP_NAME, "\n\n".join(warnings))
        else:
            messagebox.showinfo(APP_NAME, f"Saved {record['desktop_name']}")

    def _delete(self) -> None:
        if not self.current_id:
            return
        record = next((item for item in self.records if item.get("id") == self.current_id), None)
        if not record or not messagebox.askyesno(APP_NAME, f"Delete launcher '{record.get('name')}'?"):
            return
        removed = delete_launcher_files(record, self.paths)
        remove_record(self.current_id, self.paths)
        self.records = load_registry(self.paths)
        self._reset()
        self._refresh_list()
        self._log("Removed " + ", ".join(removed) if removed else "Removed launcher entry")

    def _reset(self) -> None:
        self.current_id = None
        for variable in self.vars.values():
            variable.set(False if isinstance(variable, tk.BooleanVar) else "")
        self.vars["category"].set("Game")
        self.vars["make_executable"].set(True)
        self.vars["desktop_shortcut"].set(True)
        self.vars["startup_notify"].set(True)
        self.delete_button.configure(state="disabled")
        self._update_preview()

    def _edit_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(APP_NAME, "Select a launcher from the list first.")
            return
        record_id = self.tree.item(selected[0], "values")[3]
        record = next((item for item in self.records if item.get("id") == record_id), None)
        if not record:
            return
        self.current_id = record_id
        mapping = {
            "name": "name", "comment": "comment", "source": "source_root",
            "executable": "exec_path", "icon": "icon", "workdir": "workdir",
            "args": "extra_args",
        }
        for var_name, key in mapping.items():
            self.vars[var_name].set(str(record.get(key, "")))
        self.vars["category"].set(";".join(record.get("categories", [])))
        self.vars["terminal"].set(bool(record.get("terminal")))
        self.vars["startup_notify"].set(bool(record.get("startup_notify", True)))
        self.vars["desktop_shortcut"].set(bool(record.get("desktop_shortcut", True)))
        self.delete_button.configure(state="normal")
        self.notebook.select(0)
        self._update_preview()

    def _remove_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        record_id = self.tree.item(selected[0], "values")[3]
        record = next((item for item in self.records if item.get("id") == record_id), None)
        if not record or not messagebox.askyesno(APP_NAME, f"Delete launcher '{record.get('name')}'?"):
            return
        delete_launcher_files(record, self.paths)
        remove_record(record_id, self.paths)
        if self.current_id == record_id:
            self._reset()
        self.records = load_registry(self.paths)
        self._refresh_list()
        self._log(f"Removed launcher '{record.get('name')}'")

    def _fix_paths(self) -> None:
        missing = []
        for record in self.records:
            root = Path(str(record.get("source_root", "")))
            exec_path = Path(str(record.get("exec_path", "")))
            if not root.is_dir() or not exec_path.is_file():
                missing.append(record)
        if not missing:
            messagebox.showinfo(APP_NAME, "All launcher targets still exist. Nothing to fix.")
            return

        fixed = 0
        for record in missing:
            old_root = str(record.get("source_root", ""))
            candidates = find_root_candidates(Path(old_root).name)
            new_root = ""
            if len(candidates) == 1:
                new_root = str(candidates[0])
            elif candidates:
                choice = messagebox.askyesno(
                    APP_NAME,
                    f"Multiple folders named '{Path(old_root).name}' were found:\n" +
                    "\n".join(str(item) for item in candidates) +
                    "\n\nUse the first one?",
                )
                if choice:
                    new_root = str(candidates[0])
            if not new_root:
                new_root = choose_folder(f"Find the new location of '{Path(old_root).name}'")
            if not new_root:
                self._log(f"Skipped '{record.get('name')}' (no new location chosen)")
                continue

            updated = relocate_record(record, old_root, new_root)
            target = Path(updated["exec_path"])
            if not target.is_file():
                chosen = choose_file(
                    f"Select the launcher file for '{updated['name']}'", new_root)
                if not chosen:
                    self._log(f"Skipped '{record.get('name')}' (no launcher file chosen)")
                    continue
                updated["exec_path"] = chosen
                updated["try_exec"] = chosen
            ok, message, warnings = write_launcher(updated, self.paths)
            if ok:
                upsert_record(updated, self.paths)
                fixed += 1
                self._log(f"Fixed '{updated['name']}' -> {updated['exec_path']}")
                for warning in warnings:
                    self._log("Note: " + warning)
            else:
                self._log(f"Failed to fix '{updated['name']}': {message}")

        self.records = load_registry(self.paths)
        self._refresh_list()
        messagebox.showinfo(APP_NAME, f"Fixed {fixed} of {len(missing)} launcher(s). See Status for details.")

    def _open_folder(self) -> None:
        folder = self.paths.applications_dir()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            opener = shutil.which("xdg-open") or shutil.which("gio")
            if opener:
                subprocess.Popen([opener, str(folder)] if opener.endswith("xdg-open")
                                 else [opener, "open", str(folder)])
            else:
                messagebox.showinfo(APP_NAME, str(folder))
        except OSError as exc:
            messagebox.showerror(APP_NAME, str(exc))

    # -- Preview / list ----------------------------------------------------- #

    def _update_preview(self) -> None:
        if not hasattr(self, "preview"):
            return
        try:
            record = self._record_from_form()
            if record["name"] and record["exec_path"]:
                record["id"] = self.current_id or new_record_id(
                    record["name"], record["exec_path"], self.records)
                text = build_desktop(record)
            else:
                text = "[Desktop Entry]\n# Choose a portable app to see the generated file.\n"
        except Exception as exc:  # preview must never crash the UI
            text = f"# Preview unavailable: {exc}\n"
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _icon_photo(self, path: str) -> Optional[tk.PhotoImage]:
        if not path:
            return None
        if path in self._icon_images:
            return self._icon_images[path]
        source = Path(path).expanduser()
        if not source.is_file():
            return None
        try:
            if HAS_PIL and source.suffix.lower() != ".svg":
                image = Image.open(source).convert("RGBA")
                image.thumbnail((20, 20), Image.LANCZOS)
                photo = ImageTk.PhotoImage(image)
            else:
                photo = tk.PhotoImage(file=str(source))
                factor = max(1, photo.width() // 20, photo.height() // 20)
                if factor > 1:
                    photo = photo.subsample(factor)
            self._icon_images[path] = photo
            return photo
        except Exception:
            return None

    def _refresh_list(self) -> None:
        if not hasattr(self, "tree"):
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.records = load_registry(self.paths)
        for record in self.records:
            self.tree.insert("", "end", image=self._icon_photo(str(record.get("icon", ""))), values=(
                record.get("name", ""),
                record.get("desktop_name", ""),
                record.get("source_root", ""),
                record.get("id", ""),
            ))


def main() -> None:
    migrate_legacy_config()
    LauncherApp().mainloop()


if __name__ == "__main__":
    main()
