# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin for the Steam Deck that fakes a crosshair by rewriting the MangoHud config: the performance overlay is turned into a few lines of `custom_text` (e.g. `-----` / `| + |` / `-----`) positioned at the screen center via `offset_x`/`offset_y`. Because it overwrites the MangoHud config, the performance overlay and the crosshair can't be shown at the same time, and it conflicts with other MangoHud override plugins (e.g. MangoPeel).

## Commands

- Install deps: `pnpm i`
- Build frontend (outputs `dist/index.js`): `pnpm build` (or `pnpm watch`)
- Full plugin package: `./build-zip.sh` → `out/Crosshair.zip` (needs only pnpm + python3; `--skip-frontend` reuses an existing `dist/`). It zips `dist/index.js`, `main.py`, `plugin.json`, `package.json`, `LICENSE`, `README.md` under a top-level folder named after `plugin.json`'s `name` — if you add files the backend needs at runtime, add them to the script too.
- Alternative: `.vscode/build.sh` runs `sudo decky plugin build` using the Decky CLI expected at `./cli/decky` (gitignored; requires Docker).
- Deploy to a Deck: VS Code tasks in `.vscode/tasks.json` (`builddeploy`, `deploy`) rsync/ssh using values from `.vscode/settings.json` (copy from `.vscode/defsettings.json`; `settings.json` is gitignored).

There are no tests or linters configured; `tsc` type checking happens through the rollup build (`@decky/rollup`).

## Architecture

Two halves talking over Decky's RPC bridge:

- **`main.py`** — Python backend, a `Plugin` class loaded by Decky. Every public `async` method is callable from the frontend by name. It holds in-memory state (`current_offset_x/y`, `current_style` "box"/"dot") — nothing is persisted across plugin reloads.
  - `find_mangohud_config_path()` locates the active config by scanning `/proc/*/cmdline` for `mangoapp` and reading `MANGOHUD_CONFIGFILE` from its `environ`; falls back to `~/.config/MangoHud/MangoHud.conf`, `/tmp/mangohud.conf`, then `/tmp/mangohud_crosshair.conf`. Re-resolved on every write (intentionally not cached, since the path changes per game session).
  - `write_crosshair_config()` **overwrites the entire file** with only crosshair settings.
  - `make_auto_crosshair(style, fallback_w, fallback_h)` is the only way to place a crosshair: it queries the gamescope (Xwayland) resolution with `xrandr`, using `DISPLAY`/`XAUTHORITY` from mangoapp's environment and stripping Decky's `LD_LIBRARY_PATH`; if that fails it uses the size passed from the frontend (`window.screen` × `devicePixelRatio`). Offsets are always `center − TEXT_HALF_SIZE` (no per-resolution presets). Afterwards it restarts mangoapp (SIGTERM; it is a systemd user service and respawns) unless that mangoapp PID is already recorded in `mangoapp_resolution` for the current resolution — mangoapp keeps the drawing area of the display it started on, so after switching from the 800p panel to a larger external display the crosshair is otherwise clipped/invisible. The config is written *before* the restart because the path is looked up from mangoapp's environment. Crosshair text per style lives in `CROSSHAIR_TEXT`; `adjust_crosshair_offset` re-renders using `current_style`.
- **`src/index.tsx`** — React UI (`@decky/ui` components) registered via `definePlugin`. Each backend method is bound with `callable<Args, Return>("python_method_name")`; when adding a backend method, add a matching `callable` here with the exact Python name.
- **`decky.pyi`** — type stub for the `decky` Python module provided by the loader at runtime (logger, paths, `emit`, etc.).
- **`plugin.json`** — Decky store metadata; `package.json` `version` is the plugin version.
