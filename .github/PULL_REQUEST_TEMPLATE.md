## What changed

<!-- A short description of the change. -->

## Why

<!-- Link an issue if there is one: Fixes #... -->

## Checklist

- [ ] `python3 -m py_compile pindesk.py test_portable_launcher.py` passes
- [ ] `python3 -m unittest discover -v` passes (or `xvfb-run -a ...` headless)
- [ ] Tests were added or updated for behaviour changes
- [ ] README/docs updated if behaviour or file locations changed
- [ ] CHANGELOG.md updated for user-visible changes
- [ ] No network calls, root use or execution of selected apps was introduced
- [ ] UI changes keep the single dark theme and rectangular widgets
