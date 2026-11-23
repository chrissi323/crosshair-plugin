# Crosshair Plugin

The Crosshair Plugin is a tool for the Steam Deck that overlays a crosshair on the screen. It uses MangoHud's configuration to display a customizable aiming aid, making it useful for games that don’t provide a native crosshair.

## Features

- **Auto mode**: detects the current gamescope resolution and centers the crosshair automatically, including on resolutions without a preset (e.g. 1440p, ultrawide).
- Predefined crosshairs for:
  - **800p** (Steam Deck native resolution)
  - **1080p** (external display support)
  - **2160p** (4K external displays)
- Two styles: **Box** and **Dot**.
- Adjustable offsets to fine-tune the crosshair's position.
- Displays the current x and y offsets in the UI.

## Usage

1. Open the plugin from Decky Loader.
2. Select a crosshair:
   - **Auto**: uses the current resolution. The status line shows the detected resolution and its source (`gamescope`, or `fallback` if gamescope could not be queried).
   - **800p**: For the Steam Deck's built-in screen.
   - **1080p** / **2160p**: For external displays.
3. Adjust the crosshair's position using the directional buttons (Up, Down, Left, Right).
4. View the current offsets in the plugin UI for reference.

## How It Works

- The plugin generates a MangoHud configuration file with the crosshair settings.
- Auto mode reads the screen size of gamescope's Xwayland via `xrandr` and places the crosshair at the screen center.
- Offset adjustments are handled dynamically, and the configuration is updated automatically.
- NOTE: this may conflict with any MangoHUD overrides you have set, or override plugins such as MangoPeel.

## Building

Requirements: [pnpm](https://pnpm.io/) and Python 3.

```sh
./build-zip.sh
```

This builds the frontend and creates `out/Crosshair.zip`. Install it on the Steam Deck by enabling Developer Mode in Decky Loader's settings and using **Install Plugin from ZIP File**.

Alternatively, the official [Decky CLI](https://github.com/SteamDeckHomebrew/cli) (requires Docker) can be used: `decky plugin build .`
