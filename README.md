# Crosshair Plugin

Fork of [Crosshair](https://github.com/xXJSONDeruloXx/crosshair-plugin) by **JSON Derulo** ([@xXJSONDeruloXx](https://github.com/xXJSONDeruloXx)), who came up with the idea of turning the performance overlay into a crosshair and wrote the original plugin.

The Crosshair Plugin is a tool for the Steam Deck that overlays a crosshair on the screen. It uses MangoHud's configuration to display a customizable aiming aid, making it useful for games that don’t provide a native crosshair.

## Features

- Detects the current gamescope resolution and centers the crosshair automatically — on the built-in screen as well as on external displays of any resolution (1080p, 1440p, 4K, ultrawide, ...).
- Restarts the performance overlay after a display change, so the crosshair is also visible after docking to a larger display.
- Two styles: **Box** and **Dot**.
- Manual resolution override in case auto-detection gets it wrong.
- Fine-tune the position with an adjustable nudge step (1/5/10/50 px). The correction is saved, survives reboots and is kept when switching styles or displays; **Re-center** resets it.
- Displays the current offsets and the saved correction in the UI.

## Usage

1. Open the plugin from Decky Loader.
2. Leave **Screen resolution** on *Auto-detect*. If the crosshair ends up off-center, press it to step through fixed resolutions until yours is shown.
3. Select **Make Crosshair Box** or **Make Crosshair Dot**. The status line shows the resolution used and its source (`gamescope`, `manual`, or `fallback` if gamescope could not be queried).
4. If needed, press **Nudge step** to pick the step size and move the crosshair with the directional buttons (Up, Left, Right, Down). **Re-center** puts it back in the middle.

If you switch between the built-in screen and an external display, select the crosshair again so it is re-centered for the new resolution. When the resolution has changed, the plugin briefly restarts the performance overlay (`mangoapp`), because it otherwise keeps the drawing area of the display it was started on and the crosshair would be invisible on a larger display.

## How It Works

- The plugin generates a MangoHud configuration file with the crosshair settings.
- The plugin reads the screen size of gamescope's Xwayland via `xrandr` and places the crosshair at the screen center.
- Offset adjustments are handled dynamically, and the configuration is updated automatically. Style, correction, nudge step and resolution override are stored in the plugin's Decky settings directory.
- NOTE: this may conflict with any MangoHUD overrides you have set, or override plugins such as MangoPeel.

## Download

Ready-to-install zips are attached to each [GitHub release](https://github.com/chrissi323/crosshair-plugin/releases). Install one on the Steam Deck by enabling Developer Mode in Decky Loader's settings and using **Install Plugin from ZIP File** (or install it from the release asset's URL).

Untested development builds of the `dev` branch are published as the pre-release [dev-build](https://github.com/chrissi323/crosshair-plugin/releases/tag/dev-build). Use them only for testing.

## Building

Requirements: [pnpm](https://pnpm.io/) and Python 3.

```sh
./build-zip.sh
```

This builds the frontend and creates `out/Crosshair.zip`. Install it on the Steam Deck by enabling Developer Mode in Decky Loader's settings and using **Install Plugin from ZIP File**.

Alternatively, the official [Decky CLI](https://github.com/SteamDeckHomebrew/cli) (requires Docker) can be used: `decky plugin build .`

## Credits

- **JSON Derulo** ([@xXJSONDeruloXx](https://github.com/xXJSONDeruloXx)) — original author of the plugin: [xXJSONDeruloXx/crosshair-plugin](https://github.com/xXJSONDeruloXx/crosshair-plugin).
- **kaioh1990** ([@kaioh1990](https://github.com/kaioh1990)) — the adjustable nudge step, the saved position, the **Re-center** button and the manual resolution override were shamelessly "borrowed" from the ideas in [kaioh1990/crosshair-plugin](https://github.com/kaioh1990/crosshair-plugin). Thanks!
