# Troubleshooting

## The app will not start

- Check Python and Tk: `python3 --version` and `python3 -c "import tkinter; print(tkinter.TkVersion)"`.
- Fedora/Nobara: `sudo dnf install python3-tkinter`
- Debian/Ubuntu: `sudo apt install python3-tk`
- Start it from a terminal (`python3 pindesk.py`) and read the error output.

## Auto-detect finds nothing

- Make sure the chosen folder contains an executable file (check `ls -l`).
- If the launcher is a text script without the executable bit, select it manually
  with **Browse** next to *Launcher file* and keep **Make launcher file executable if needed** checked.
- Shared libraries are intentionally excluded.

## Auto-detect picks the wrong file

Use the *Launcher file* dropdown. Prefer the top-level wrapper script. If the
right file is not listed, browse for it directly.

## No icon was found

Put an `icon.png` or `icon.svg` in the app folder, or choose one with **Browse**
next to *Icon*. PinDesk will otherwise generate a simple initials SVG.

## The desktop icon refuses to launch

Right-click it and choose **Allow Launching**. This is a desktop-environment
trust rule, not a bad launcher. If the application-menu entry works, the file is
fine.

## PinDesk is missing from the application menu

Run `bash install.sh` from the cloned folder. Log out and back in if your menu
caches entries. `bash uninstall.sh` removes just this entry.

## A launcher stopped working after moving the drive

Open **Manage** → **Fix moved app folders…**. If automatic relocation cannot
find a target, use **Edit selected** and browse for the new executable and icon.

## Validation warns about my launcher

Install `desktop-file-validate` (`desktop-file-utils`) to get the exact message.
Check the **Show .desktop preview** output; unusual characters in names or
arguments are the usual cause.

## Settings seem to have vanished after upgrading

PinDesk 1.0 moved its config folder from `~/.config/portable-launcher/` to
`~/.config/pindesk/`. Migration happens automatically on first run. If you had
moved or copied the folder manually, move it yourself and start PinDesk again.
