# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin for the Steam Deck that fakes a crosshair by rewriting the MangoHud config: the performance overlay is turned into a few lines of `custom_text` (e.g. `-----` / `| + |` / `-----`) positioned at the screen center via `offset_x`/`offset_y`. Because it overwrites the MangoHud config, the performance overlay and the crosshair can't be shown at the same time, and it conflicts with other MangoHud override plugins (e.g. MangoPeel).

## Commands

- Install deps: `pnpm i`
- Build frontend (outputs `dist/index.js`): `pnpm build` (or `pnpm watch`)
- Full plugin package: `./build-zip.sh` → `out/Crosshair.zip` (needs only pnpm + python3; `--skip-frontend` reuses an existing `dist/`). It zips `dist/index.js`, `main.py`, `plugin.json`, `package.json`, `LICENSE`, `README.md` under a top-level folder named after `plugin.json`'s `name` — if you add files the backend needs at runtime, add them to the script too.
- Alternative: `.vscode/build.sh` runs `sudo decky plugin build` using the Decky CLI expected at `./cli/decky` (gitignored; requires Docker).
- Branches and releases (`.github/workflows/release.yml`):
  - `main` = stable, matches the latest release. Untested work goes to `dev`; every push to `dev` builds the zip and replaces the asset of the pre-release `dev-build` (tag moved to that commit), downloadable at `https://github.com/chrissi323/crosshair-plugin/releases/download/dev-build/Crosshair.zip`. The user tests that on the Steam Deck (nothing can be tested on-device here).
  - Only after the user confirms a dev build works: fast-forward `main` to `dev`, bump `version` in `package.json`, commit, push a matching tag (`git tag -a vX.Y.Z -m "Release X.Y.Z" && git push origin main vX.Y.Z`) → stable release with the zip; fails if the tag doesn't match `package.json`. Don't tag intermediate fixes.
  - A manual run (`workflow_dispatch`) only uploads the zip as a workflow artifact.
- Deploy to a Deck: VS Code tasks in `.vscode/tasks.json` (`builddeploy`, `deploy`) rsync/ssh using values from `.vscode/settings.json` (copy from `.vscode/defsettings.json`; `settings.json` is gitignored).

There are no tests or linters configured; `tsc` type checking happens through the rollup build (`@decky/rollup`).

## Architecture

Two halves talking over Decky's RPC bridge:

- **`main.py`** — Python backend, a `Plugin` class loaded by Decky. Every public `async` method is callable from the frontend by name. State is described below (settings are persisted, the shown offsets are not).
  - `find_mangohud_config_path()` locates the active config by scanning `/proc/*/cmdline` for `mangoapp` and reading `MANGOHUD_CONFIGFILE` from its `environ`; falls back to `~/.config/MangoHud/MangoHud.conf`, `/tmp/mangohud.conf`, then `/tmp/mangohud_crosshair.conf`. Re-resolved on every write (intentionally not cached, since the path changes per game session).
  - `write_crosshair_config()` **overwrites the entire file** with only crosshair settings.
  - `place_crosshair()` is the single code path that writes a visible crosshair (used by `make_crosshair`, `recenter_crosshair`, `set_resolution_mode`). Resolution: manual override (`resolution_mode` "WIDTHxHEIGHT") → gamescope (Xwayland) via `xrandr`, using `DISPLAY`/`XAUTHORITY` from mangoapp's environment and stripping Decky's `LD_LIBRARY_PATH` → size passed from the frontend (`window.screen` × `devicePixelRatio`). Offset = `center − TEXT_HALF_SIZE + nudge`. Returns `[w, h, source, restarted]`, which the frontend shows in the status line. `[w, h, source]` is also kept in `last_placement` for the hint under the resolution dropdown. Choices in the frontend use `ChoiceItem` (a `ButtonItem` showing the value + `showContextMenu`) instead of `DropdownItem`: Steam's dropdown only refreshed its label after a focus change, and re-rendering while it closed made it pop open again. `onChoose` handlers update local state immediately and defer the backend call (`MENU_ACTION_DELAY_MS`).
  - mangoapp restart: after writing, it SIGTERMs mangoapp (a systemd user service that respawns) unless that PID is already recorded in `mangoapp_resolution` for the *detected* resolution (not the override) — mangoapp keeps the drawing area of the display it started on, so after switching from the 800p panel to a larger external display the crosshair is otherwise clipped/invisible. The config is written *before* the restart because the path is looked up from mangoapp's environment.
  - Persistence: `settings` (style, `nudge_x/y` = correction relative to center, `nudge_step`, `resolution_mode`) is saved as JSON in `decky.DECKY_PLUGIN_SETTINGS_DIR` and validated against `DEFAULT_SETTINGS` on load. `current_offset_x/y` (None = no crosshair shown) is runtime-only — after a reboot Steam rewrites the MangoHud config anyway. Arrow buttons change the saved nudge even when no crosshair is shown.
- **`src/index.tsx`** — React UI (`@decky/ui` components) registered via `definePlugin`. Each backend method is bound with `callable<Args, Return>("python_method_name")`; when adding a backend method, add a matching `callable` here with the exact Python name.
- **`decky.pyi`** — type stub for the `decky` Python module provided by the loader at runtime (logger, paths, `emit`, etc.).
- **`plugin.json`** — Decky store metadata; `package.json` `version` is the plugin version.
