# Security policy

## Scope

PinDesk reads local files and writes `.desktop` entries under the user's own
`$HOME`. It does not run selected applications, make network requests, use root
privileges or ship telemetry.

## Reporting a vulnerability

Please report security concerns privately through GitHub's **Security → Report a
vulnerability** feature on the repository, or contact the maintainer directly.
Include reproduction steps and the affected version. You should receive an
acknowledgement within a week. Please give us a reasonable time to fix the issue
before disclosing it publicly.

## Supported versions

| Version | Supported |
| --- | --- |
| 1.0.x | Yes |

## Threat model notes

- A `.desktop` file is executable configuration. PinDesk validates generated
  files and quotes all paths, but users should still check the preview for
  untrusted bundles.
- Icons and scripts in an app folder are only read, never executed.
- The launcher registry is JSON under `~/.config/pindesk/`; it contains paths,
  not secrets.
