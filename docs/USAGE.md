# Using PinDesk

## Create a launcher

1. **Choose the app folder.** Click **Browse** next to *App folder*. The native
   dialog of your desktop environment is used when available (`kdialog` on KDE,
   then `zenity`/`yad`, then the built-in Tk dialog). You can also paste a path.
2. **Auto-detect.** PinDesk scans the folder and its `bin/` directory and fills
   in:
   - **Launcher file** — the executable or wrapper script
   - **Name** — derived from the folder name, cleaned of version/platform noise
   - **Icon** — a local icon, if one is found
   - **Working directory** — the app folder
3. **Pick the right target** from the *Launcher file* dropdown if several are
   found. Prefer a shell script with a name like `run`, `start` or the app name:
   it usually sets up the portable environment. Shared libraries are excluded.
4. **Adjust optional fields.** **More options** reveals comment, working
   directory, extra arguments, terminal flag and the executable-permission
   option. Leave *Make launcher file executable if needed* on for wrappers that
   are not yet executable.
5. **Preview** the file with **Show .desktop preview**: the preview is generated
   with exactly the same code that writes the launcher.
6. **Add launcher.** PinDesk validates the file with `desktop-file-validate`
   when available, writes it to `~/.local/share/applications/`, optionally copies
   it to `~/Desktop/`, refreshes the desktop database and records it in its registry.

Most apps need nothing beyond steps 1, 2 and 6.

## Manage launchers

The **Manage** tab lists every launcher PinDesk created, with its icon.

- **Edit selected** — loads a launcher back into the Create tab.
- **Remove selected** — deletes the `.desktop` file(s) and registry entry.
- **Open folder** — opens the portable app's folder in your file manager.
- **Fix moved app folders…** — when a USB drive mounts at a new path, updates
  `Exec=`, `Path=`, `TryExec=` and `Icon=` for all affected launchers.
- **Refresh list** — reloads the registry.

Status messages from the last operation appear at the bottom of the window.

## Desktop icons

By default a shortcut is also placed on your Desktop. PinDesk tries to mark it
trusted with `gio set metadata::trusted`. GNOME honours this. On KDE Plasma and
XFCE you may need to right-click the icon once and choose **Allow Launching**.
Application-menu entries are not affected by desktop trust rules.

## Moving or deleting PinDesk

To move the installation, close the app, move the folder, then run `bash
install.sh` in the new location to update its own menu entry. To uninstall, run
`bash uninstall.sh`, remove your launchers from the Manage tab, and delete
`~/.config/pindesk/`.
