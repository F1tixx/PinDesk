#!/usr/bin/env python3
"""Offline tests for pindesk.py (no GUI window is opened)."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import pindesk as pl


class FakeHome:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pindesk-test-")
        self.home = Path(self.tmp.name)
        (self.home / "Desktop").mkdir()
        self.paths = pl.Paths(self.home)

    def close(self):
        self.tmp.cleanup()


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHome()
        self.old_paths = pl.PATHS
        pl.PATHS = self.fake.paths

    def tearDown(self):
        pl.PATHS = self.old_paths
        self.fake.close()

    def make_app(self, folder_name="PrismLauncher-Linux-Qt6-Portable-11.1.1"):
        root = self.fake.home / "apps" / folder_name
        root.mkdir(parents=True)
        wrapper = root / "PrismLauncher"
        wrapper.write_text(
            "#!/usr/bin/env bash\n"
            "LAUNCHER_DIR=\"$(dirname \"$(readlink -f \"$0\")\")\"\n"
            "if [ -f portable.txt ]; then echo portable; fi\n"
            "exec \"${LAUNCHER_DIR}/bin/prismlauncher\"\n"
        )
        wrapper.chmod(0o755)
        (root / "portable.txt").write_text("portable mode\n")
        (root / "bin").mkdir()
        inner = root / "bin" / "prismlauncher"
        inner.write_bytes(b"\x7fELF")
        inner.chmod(0o755)
        (root / "icons").mkdir()
        (root / "icons" / "other.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (root / "icon.png").write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x80\x00\x00\x00\x80\x08\x06\x00\x00\x00"
        )
        return root, wrapper

    def test_escape_field(self):
        self.assertEqual(pl.escape_field("a;b\\c\nd\te"), "a\\;b\\\\c\\nd\\te")

    def test_quote_exec_arg(self):
        self.assertEqual(pl.quote_exec_arg("/usr/bin/true"), "/usr/bin/true")
        self.assertEqual(pl.quote_exec_arg("/tmp/My Apps/run"), '"/tmp/My Apps/run"')
        self.assertIn("\\\\$", pl.quote_exec_arg("/tmp/Cash$Flow/run"))
        self.assertEqual(pl.quote_exec_arg("/tmp/100%/run"), "/tmp/100%%/run")
        self.assertEqual(pl.quote_exec_arg(""), '""')

    def test_guess_name(self):
        self.assertEqual(
            pl.guess_name(Path("PrismLauncher-Linux-Qt6-Portable-11.1.1")),
            "Prism Launcher",
        )
        self.assertEqual(pl.guess_name(Path("my_cool_app")), "My Cool App")

    def test_detect_fields_prism_like(self):
        root, wrapper = self.make_app()
        detected = pl.detect_fields(root, self.fake.paths)
        self.assertEqual(detected["name"], "Prism Launcher")
        self.assertEqual(detected["exec_path"], str(wrapper))
        self.assertEqual(detected["workdir"], str(root))
        self.assertEqual(detected["source_root"], str(root))
        self.assertEqual(detected["icon"], str((root / "icon.png").resolve()))
        text = pl.build_desktop({**detected, "id": "prism-launcher"})
        self.assertIn("[Desktop Entry]", text)
        self.assertNotIn("#!", text)
        self.assertIn("Path=" + str(root), text)
        self.assertIn("TryExec=" + str(wrapper), text)
        self.assertIn("Categories=Game;", text)
        valid, output = pl.validate_desktop_text(text)
        self.assertTrue(valid, output)

    def test_exec_escaping_validates_with_real_paths(self):
        if not shutil.which("desktop-file-validate"):
            self.skipTest("desktop-file-validate not installed")
        for folder in ("My Apps", "Cash$Flow", "100%", 'a"b', "back\\slash"):
            target = self.fake.home / "weird" / folder / "run"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("#!/bin/sh\nexit 0\n")
            target.chmod(0o755)
            record = {
                "id": "weird", "name": "Weird " + folder, "comment": "a;b\\c",
                "exec_path": str(target), "try_exec": str(target),
                "icon": "", "workdir": str(target.parent),
                "categories": ["Game"], "terminal": False, "startup_notify": True,
            }
            text = pl.build_desktop(record)
            valid, output = pl.validate_desktop_text(text)
            self.assertTrue(valid, f"{folder}: {output}\n{text}")

    def test_detection_skips_shared_libraries_and_matching_name(self):
        root = self.fake.home / "P.T. Silent Hill Demo"
        root.mkdir(parents=True)
        # Shared libraries often have +x set; they must never be launch targets.
        for name in ("libamd_fidelityfx_vk.so", "libnvidia-ngx-dlss.so.310.9.1"):
            lib = root / name
            lib.write_bytes(b"\x7fELF")
            lib.chmod(0o755)
        game = root / "pt"
        game.write_bytes(b"\x7fELF")
        game.chmod(0o755)
        updater = root / "pt-updater"
        updater.write_bytes(b"\x7fELF")
        updater.chmod(0o755)
        (root / "pt-icon.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        detected = pl.detect_fields(root, self.fake.paths)
        self.assertEqual(detected["exec_path"], str(game))
        self.assertEqual(detected["icon"], str((root / "pt-icon.png").resolve()))
        self.assertNotIn(str(root / "libamd_fidelityfx_vk.so"), detected["exec_candidates"])

    def test_lone_executable_uses_file_name(self):
        target = self.fake.home / "my-cool-tool"
        target.write_text("#!/bin/sh\nexit 0\n")
        target.chmod(0o755)
        detected = pl.detect_fields(target, self.fake.paths)
        self.assertEqual(detected["name"], "My Cool Tool")
        self.assertEqual(detected["exec_path"], str(target))

    def test_write_registry_and_delete(self):
        root, wrapper = self.make_app()
        detected = pl.detect_fields(root, self.fake.paths)
        record = {**detected, "id": "prism-launcher", "desktop_name": "prism-launcher.desktop"}
        ok, message, warnings = pl.write_launcher(record, self.fake.paths)
        self.assertTrue(ok, message)
        target = self.fake.paths.applications_dir() / "prism-launcher.desktop"
        self.assertTrue(target.is_file())
        self.assertTrue((self.fake.paths.desktop_dir() / "prism-launcher.desktop").is_file())
        self.assertEqual(pl.load_registry(self.fake.paths), [])
        pl.upsert_record(record, self.fake.paths)
        self.assertEqual(pl.load_registry(self.fake.paths)[0]["id"], "prism-launcher")
        removed = pl.delete_launcher_files(record, self.fake.paths)
        self.assertEqual(len(removed), 2)
        self.assertFalse(target.exists())

    def test_relocate(self):
        record = {
            "name": "App", "source_root": "/mnt/old/MyApp",
            "exec_path": "/mnt/old/MyApp/start",
            "try_exec": "/mnt/old/MyApp/start",
            "workdir": "/mnt/old/MyApp",
            "icon": "/mnt/old/MyApp/icon.png",
        }
        moved = pl.relocate_record(record, "/mnt/old/MyApp", "/mnt/new/MyApp")
        self.assertEqual(moved["exec_path"], "/mnt/new/MyApp/start")
        self.assertEqual(moved["icon"], "/mnt/new/MyApp/icon.png")
        self.assertEqual(moved["source_root"], "/mnt/new/MyApp")
        self.assertEqual(record["exec_path"], "/mnt/old/MyApp/start")

    def test_fallback_icon_is_svg(self):
        icon = Path(pl.fallback_icon("Prism Launcher", self.fake.paths))
        self.assertTrue(icon.is_file())
        self.assertIn("<svg", icon.read_text())
        self.assertIn("PL", icon.read_text())

    def test_icon_prefers_root_over_cache(self):
        root, _ = self.make_app()
        (root / "cache").mkdir()
        (root / "cache" / "icon.png").write_bytes(b"not a png")
        icon = pl.find_icon(root, root / "PrismLauncher", "Prism Launcher")
        self.assertEqual(icon, str((root / "icon.png").resolve()))

    def test_ids_are_unique(self):
        self.assertEqual(pl.new_record_id("My App", "/a", []), "my-app")
        second = pl.new_record_id("My App", "/b", [{"id": "my-app"}])
        self.assertTrue(second.startswith("my-app-"))
        name = pl.desktop_name_for("my-app", [{"id": "other", "desktop_name": "my-app.desktop"}])
        self.assertNotEqual(name, "my-app.desktop")


class DummyVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DummyPreview:
    def __init__(self):
        self.text = ""

    def configure(self, **kwargs):
        pass

    def delete(self, *_args):
        self.text = ""

    def insert(self, _position, text):
        self.text += text


class FormTests(unittest.TestCase):
    """Exercise the form/preview logic without opening a Tk window."""

    def setUp(self):
        self.fake = FakeHome()
        self.app = object.__new__(pl.LauncherApp)
        self.app.paths = self.fake.paths
        self.app.records = []
        self.app.current_id = None
        self.app.preview = DummyPreview()
        self.app.vars = {
            "source": DummyVar(""), "executable": DummyVar(""),
            "make_executable": DummyVar(True),
            "name": DummyVar("Prism Launcher"), "comment": DummyVar("Portable Minecraft launcher"),
            "icon": DummyVar(""), "workdir": DummyVar(""), "category": DummyVar("Game"),
            "args": DummyVar(""), "terminal": DummyVar(False),
            "startup_notify": DummyVar(True), "desktop_shortcut": DummyVar(True),
        }
        self.target = self.fake.home / "run"
        self.target.write_text("#!/bin/sh\nexit 0\n")
        self.target.chmod(0o755)
        self.app.vars["executable"].set(str(self.target))
        self.app.vars["workdir"].set(str(self.target.parent))

    def tearDown(self):
        self.fake.close()

    def test_record_from_form(self):
        record = self.app._record_from_form()
        self.assertEqual(record["name"], "Prism Launcher")
        self.assertEqual(record["exec_path"], str(self.target))
        self.assertEqual(record["categories"], ["Game"])
        self.assertTrue(self.app._form_valid(record))

    def test_preview_generated(self):
        self.app._update_preview()
        self.assertIn("[Desktop Entry]", self.app.preview.text)
        self.assertIn("Exec=" + str(self.target), self.app.preview.text)
        self.assertIn("TryExec=" + str(self.target), self.app.preview.text)


class ThemeTests(unittest.TestCase):
    """The definitive build has one dark theme and plain rectangular widgets."""

    def setUp(self):
        self.app = pl.LauncherApp()
        self.app.withdraw()

    def tearDown(self):
        self.app.destroy()

    def test_no_theme_switcher(self):
        self.assertFalse(hasattr(self.app, "theme_var"))
        self.assertFalse(hasattr(pl, "load_settings"))
        self.assertFalse(hasattr(pl, "save_settings"))

    def test_dark_colours_applied_to_all_widgets(self):
        from tkinter import ttk
        style = ttk.Style()
        c = pl.THEME
        for widget, option, expected in (
            ("TEntry", "fieldbackground", c["field"]),
            ("TEntry", "foreground", c["fg"]),
            ("TCombobox", "fieldbackground", c["field"]),
            ("TButton", "background", c["surface"]),
            ("Accent.TButton", "background", c["accent"]),
            ("Treeview", "fieldbackground", c["field"]),
            ("Treeview", "foreground", c["fg"]),
            ("TNotebook.Tab", "foreground", c["fg"]),
        ):
            self.assertEqual(style.lookup(widget, option), expected,
                             f"{widget}.{option}")
        for widget in (self.app.preview, self.app.status):
            self.assertEqual(widget.cget("bg"), c["field"])
            self.assertEqual(widget.cget("fg"), c["fg"])

    def test_plain_rectangular_widgets(self):
        from tkinter import ttk
        style = ttk.Style()
        self.assertIn("Button.border", str(style.layout("TButton")))
        self.assertIn("Entry.field", str(style.layout("TEntry")))


class BrandingTests(unittest.TestCase):
    def test_app_identity(self):
        self.assertEqual(pl.APP_NAME, "PinDesk")
        self.assertEqual(pl.APP_VERSION, "1.0.1")

    def test_app_icon_files_exist(self):
        icon = pl.app_icon_path()
        self.assertIsNotNone(icon)
        self.assertEqual(Path(icon).name, "logo.png")
        self.assertTrue(Path(icon).is_file())
        self.assertTrue(pl.APP_LOGO_SVG.is_file())

    def test_window_uses_app_icon(self):
        app = pl.LauncherApp()
        app.withdraw()
        try:
            self.assertIsNotNone(app.icon_image)
        finally:
            app.destroy()

    def test_config_migration_preserves_registry(self):
        with tempfile.TemporaryDirectory(prefix="pindesk-migrate-") as directory:
            home = Path(directory)
            legacy = home / ".config" / "portable-launcher"
            legacy.mkdir(parents=True)
            (legacy / "launchers.json").write_text(
                '{"schema": 1, "launchers": [{"id": "old"}]}', encoding="utf-8")
            paths = pl.Paths(home)
            self.assertTrue(pl.migrate_legacy_config(paths))
            self.assertFalse(legacy.exists())
            self.assertEqual([r["id"] for r in pl.load_registry(paths)], ["old"])
            self.assertFalse(pl.migrate_legacy_config(paths))


if __name__ == "__main__":
    unittest.main(verbosity=2)
