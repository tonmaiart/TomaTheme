# TomaTheme

Tomatactics: a Blender 5.1+ add-on for a clean, tuned interface theme, viewport background presets,
quick fullscreen / guides / UI scale toggles, and transparent viewport renders. It lives in the 3D View
sidebar under the **Theme** tab.

## Install

1. Open the [latest release](https://github.com/tonmaiart/TomaTheme/releases/latest).
2. Download `Tomatactics-<version>.zip` from **Assets** (not "Source code").
3. Drag the zip into any Blender window and confirm, or use
   **Edit > Preferences > Get Extensions > Install from Disk**.

## Releasing

Register the alias once per clone:

```sh
git config alias.release-app '!bash "$(git rev-parse --show-toplevel)/scripts/release-app.sh"'
```

Bump `version` in `blender_manifest.toml`, then from `main`:

```sh
git release-app
```

It commits any uncommitted changes, pushes `main`, moves the `X.Y.Z` tag to HEAD and pushes it, then
waits for `.github/workflows/release.yml`, which builds the zip and publishes the GitHub Release.
Requires the [GitHub CLI](https://cli.github.com/) (`gh auth login` once).

To build the zip locally without releasing: `python scripts/build_zip.py` (output in `dist/`).
