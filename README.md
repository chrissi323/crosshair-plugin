# Crosshair Plugin

The Crosshair Plugin is a tool for the Steam Deck that overlays a crosshair on the screen. It uses MangoHud's configuration to display a customizable aiming aid, making it useful for games that don’t provide a native crosshair.

## Features

- Detects the current gamescope resolution and centers the crosshair automatically — on the built-in screen as well as on external displays of any resolution (1080p, 1440p, 4K, ultrawide, ...).
- Two styles: **Box** and **Dot**.
- Adjustable offsets to fine-tune the crosshair's position.
- Displays the current x and y offsets in the UI.

## Usage

1. Open the plugin from Decky Loader.
2. Select **Make Crosshair Box** or **Make Crosshair Dot**. The status line shows the detected resolution and its source (`gamescope`, or `fallback` if gamescope could not be queried).
3. Adjust the crosshair's position using the directional buttons (Up, Down, Left, Right).
4. View the current offsets in the plugin UI for reference.

If you switch between the built-in screen and an external display, select the crosshair again so it is re-centered for the new resolution. When the resolution has changed, the plugin briefly restarts the performance overlay (`mangoapp`), because it otherwise keeps the drawing area of the display it was started on and the crosshair would be invisible on a larger display.

## How It Works

- The plugin generates a MangoHud configuration file with the crosshair settings.
- The plugin reads the screen size of gamescope's Xwayland via `xrandr` and places the crosshair at the screen center.
- Offset adjustments are handled dynamically, and the configuration is updated automatically.
- NOTE: this may conflict with any MangoHUD overrides you have set, or override plugins such as MangoPeel.

## Building

Requirements: [pnpm](https://pnpm.io/) and Python 3.

```sh
./build-zip.sh
```

This builds the frontend and creates `out/Crosshair.zip`. Install it on the Steam Deck by enabling Developer Mode in Decky Loader's settings and using **Install Plugin from ZIP File**.

Alternatively, the official [Decky CLI](https://github.com/SteamDeckHomebrew/cli) (requires Docker) can be used: `decky plugin build .`
