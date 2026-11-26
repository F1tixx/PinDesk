# FAQ

### Does PinDesk run the app I select?

No. It only reads files and writes `.desktop` text. The selected program is
never executed by PinDesk.

### Does it need internet access?

No. Icon search is local only. PinDesk makes no network requests.

### Why does my launcher need a wrapper script instead of the binary inside `bin/`?

Portable bundles commonly set `LD_LIBRARY_PATH`, Qt plugin paths or other
variables in a start script. Launching the inner binary skips that setup and
usually fails. PinDesk prefers the wrapper.

### Why is `Path=` important?

Many portable apps check for `portable.txt` relative to the current directory.
Without `Path=`, the app starts from your home directory and silently loses
portable mode.

### My desktop icon says "Untrusted". What now?

On KDE Plasma and XFCE, right-click the Desktop icon and choose **Allow
Launching**. Menu entries in `~/.local/share/applications/` do not have this
restriction.

### Can I use it with AppImages?

Yes. Select the AppImage as the launcher file. PinDesk uses an icon file next to
it if one exists; it does not extract icons from inside the AppImage.

### It picked the wrong executable. How do I fix it?

Use the *Launcher file* dropdown in the Create tab to choose another detected
target, or browse manually. Shared libraries are never listed.

### My USB drive now mounts at a different path. Do I have to recreate everything?

No. Open the **Manage** tab and click **Fix moved app folders…**. PinDesk finds
launchers whose targets moved and rewrites their paths.

### Does it support Windows or macOS?

No. PinDesk generates freedesktop `.desktop` entries and is Linux-only.

### Where are my launchers stored?

`~/.local/share/applications/`. PinDesk's own registry and generated icons live
in `~/.config/pindesk/`.

### Can I use light mode?

No. The definitive release intentionally ships a single dark theme to avoid
style bugs and keep the UI consistent.
