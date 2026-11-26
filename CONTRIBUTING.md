# Contributing to PinDesk

Thanks for helping out. PinDesk is deliberately small, so contributions are
easiest when they keep it that way.

## Ground rules

- PinDesk stays a single Python file with no mandatory third-party dependencies.
- It must never execute the app a user selects, never access the network and
  never require root.
- New behaviour should come with an offline test in `test_portable_launcher.py`.
- UI changes must keep the single dark theme and plain rectangular widgets.

## Development setup

```sh
git clone https://github.com/F1tixx/PinDesk.git
cd PinDesk
python3 -m unittest discover -v
python3 pindesk.py
```

On Debian/Ubuntu you may need `sudo apt install python3-tk`. On headless
machines, run the tests with `xvfb-run -a python3 -m unittest discover -v`.

Useful optional tools: `desktop-file-validate` (validation), `kdialog` or
`zenity` (native dialogs), `Pillow` (better icon scaling).

## Before opening a pull request

1. `python3 -m py_compile pindesk.py test_portable_launcher.py`
2. `python3 -m unittest discover -v` — all tests must pass.
3. Manually try the change in the GUI if it touches the UI.
4. Update the README/docs if behaviour or file locations changed.
5. Add a line to `CHANGELOG.md` for user-visible changes.

## Reporting bugs

Use the bug report issue template and include:

- Linux distribution and desktop environment
- Python and Tk versions (`python3 --version`)
- Exact steps to reproduce
- The generated `.desktop` file (with the **Show .desktop preview** button)
- Anything from Status, plus stderr output if you started PinDesk from a terminal

Please do not include private paths or personal data you do not want shared.

## Code style

- Follow the surrounding code: plain functions, type hints, no classes where a function is enough.
- Keep file writes atomic through `_atomic_write`.
- Desktop Entry values must go through `escape_field()` and `quote_exec_arg()`.

## Security issues

Do not open a public issue. Follow [SECURITY.md](SECURITY.md) instead.

By participating you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).
