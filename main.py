import asyncio
import json
import os
import re
import signal
import subprocess
import decky

# Half the rendered crosshair text size in pixels; the crosshair is placed at
# "screen center minus this" (see compute_offsets).
TEXT_HALF_SIZE = {"box": (22, 20), "dot": (9, 20)}
CROSSHAIR_TEXT = {"box": ("-----", "| + |", "-----"), "dot": (" ", "+", " ")}
NUDGE_STEPS = (1, 5, 10, 50)
# Persisted between plugin reloads and reboots (see load_settings/save_settings).
DEFAULT_SETTINGS = {
    "style": "box",
    "nudge_x": 0,  # manual correction relative to the computed screen center
    "nudge_y": 0,
    "nudge_step": 5,
    "resolution_mode": "auto",  # "auto" or "WIDTHxHEIGHT"
}


class Plugin:
    def __init__(self):
        # Offsets of the crosshair currently written to the config, None if none is shown
        self.current_offset_x = None
        self.current_offset_y = None
        self.settings = dict(DEFAULT_SETTINGS)
        # mangoapp keeps the drawing area of the display it was started on, so after
        # switching to a larger display it must be restarted. Remembers, per mangoapp
        # PID, the resolution it is known to be valid for.
        self.mangoapp_resolution = {}

    def find_mangoapp_pid(self):
        """Return the PID of the running mangoapp process, or None"""
        for proc_dir in os.listdir("/proc"):
            if not proc_dir.isdigit():
                continue
            try:
                with open(f"/proc/{proc_dir}/cmdline", "r") as f:
                    argv0 = f.read().split("\0", 1)[0]
            except (FileNotFoundError, PermissionError, IOError):
                # Skip processes we can't read
                continue
            if os.path.basename(argv0) == "mangoapp":
                return int(proc_dir)
        return None

    def find_mangoapp_environ(self):
        """Return the environment of the running mangoapp process as a dict, or None"""
        pid = self.find_mangoapp_pid()
        if pid is None:
            return None
        try:
            with open(f"/proc/{pid}/environ", "r") as f:
                environ = f.read()
        except (FileNotFoundError, PermissionError, IOError):
            return None
        return dict(var.split("=", 1) for var in environ.split("\0") if "=" in var)

    async def restart_mangoapp(self, pid: int):
        """Terminate mangoapp; it runs as a systemd user service and is restarted
        automatically, picking up the current display size. Returns the new PID or None."""
        decky.logger.info(f"Restarting mangoapp (PID {pid}) for the new display size")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(40):  # wait up to 10 s
            await asyncio.sleep(0.25)
            new_pid = self.find_mangoapp_pid()
            if new_pid is not None and new_pid != pid:
                decky.logger.info(f"mangoapp restarted with PID {new_pid}")
                return new_pid
        decky.logger.warning("mangoapp did not come back after restart")
        return None

    def find_mangohud_config_path(self):
        """Find the active MangoHUD config file path by looking for mangoapp process"""
        try:
            environ = self.find_mangoapp_environ()
            if environ and environ.get("MANGOHUD_CONFIGFILE"):
                config_path = environ["MANGOHUD_CONFIGFILE"]
                decky.logger.info(f"Found MangoHUD config file: {config_path}")
                return config_path

            # If no mangoapp process found, try common config locations
            common_paths = [
                os.path.expanduser("~/.config/MangoHud/MangoHud.conf"),
                "/tmp/mangohud.conf",
                "/tmp/MangoHud.conf"
            ]
            
            for path in common_paths:
                if os.path.exists(path):
                    decky.logger.info(f"Using fallback MangoHUD config: {path}")
                    return path
            
            # Create a default config if none exists
            default_path = "/tmp/mangohud_crosshair.conf"
            decky.logger.info(f"No MangoHUD config found, creating default: {default_path}")
            return default_path
            
        except Exception as e:
            decky.logger.error(f"Error finding MangoHUD config: {str(e)}")
            # Fallback to default location
            return "/tmp/mangohud_crosshair.conf"

    async def write_crosshair_config(self, custom_text_1: str, custom_text_2: str, custom_text_3: str, offset_x: int, offset_y: int):
        try:
            # Always find the current MangoHUD config path - don't cache it
            config_path = self.find_mangohud_config_path()

            # Build crosshair config - ONLY crosshair settings, nothing else
            crosshair_config = f"""legacy_layout=false
background_alpha=0
alpha=1
background_color=020202
text_color=FF007B
custom_text={custom_text_1}
custom_text={custom_text_2}
custom_text={custom_text_3}
offset_x={offset_x}
offset_y={offset_y}"""

            # Write ONLY the crosshair config, overwriting the entire file
            with open(config_path, "w") as f:
                f.write(crosshair_config)

            decky.logger.info(f"Crosshair configuration written to {config_path}")
            
        except Exception as e:
            decky.logger.error(f"Error in write_crosshair_config: {str(e)}")
            raise e

    def get_gamescope_resolution(self):
        """Query the current screen size of gamescope's Xwayland via xrandr.

        DISPLAY/XAUTHORITY are taken from mangoapp, which runs inside gamescope.
        Returns (width, height) or None.
        """
        mangoapp_env = self.find_mangoapp_environ() or {}
        env = dict(os.environ)
        # Decky's bundled Python sets LD_LIBRARY_PATH, which breaks system binaries
        env.pop("LD_LIBRARY_PATH", None)

        displays = [mangoapp_env["DISPLAY"]] if mangoapp_env.get("DISPLAY") else []
        displays += [d for d in (":0", ":1") if d not in displays]
        if mangoapp_env.get("XAUTHORITY"):
            env["XAUTHORITY"] = mangoapp_env["XAUTHORITY"]

        for display in displays:
            env["DISPLAY"] = display
            try:
                result = subprocess.run(
                    ["xrandr", "--current"], env=env, capture_output=True, text=True, timeout=3
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                decky.logger.warning(f"xrandr failed on {display}: {e}")
                continue
            match = re.search(r"current (\d+) x (\d+)", result.stdout)
            if result.returncode == 0 and match:
                width, height = int(match.group(1)), int(match.group(2))
                decky.logger.info(f"gamescope resolution on {display}: {width}x{height}")
                return width, height
            decky.logger.warning(f"xrandr on {display} gave no resolution: {result.stderr.strip()}")
        return None

    # ------------------------------------------------------------------ #
    # Settings persistence
    # ------------------------------------------------------------------ #
    def settings_path(self):
        return os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")

    def load_settings(self):
        try:
            with open(self.settings_path(), "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            decky.logger.error(f"Could not load settings: {e}")
            return
        for key, default in DEFAULT_SETTINGS.items():
            if isinstance(data.get(key), type(default)):
                self.settings[key] = data[key]
        if self.settings["style"] not in CROSSHAIR_TEXT:
            self.settings["style"] = DEFAULT_SETTINGS["style"]
        if self.settings["nudge_step"] not in NUDGE_STEPS:
            self.settings["nudge_step"] = DEFAULT_SETTINGS["nudge_step"]
        if self.parse_resolution_mode(self.settings["resolution_mode"]) is None:
            self.settings["resolution_mode"] = "auto"

    def save_settings(self):
        try:
            path = self.settings_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(self.settings, f)
        except OSError as e:
            decky.logger.error(f"Could not save settings: {e}")

    @staticmethod
    def parse_resolution_mode(mode: str):
        """"auto" -> "auto", "WIDTHxHEIGHT" -> (width, height), anything else -> None"""
        if mode == "auto":
            return "auto"
        match = re.fullmatch(r"(\d+)x(\d+)", mode or "")
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    # ------------------------------------------------------------------ #
    # Placing the crosshair
    # ------------------------------------------------------------------ #
    @staticmethod
    def compute_offsets(style: str, width: int, height: int):
        half_w, half_h = TEXT_HALF_SIZE[style]
        return width // 2 - half_w, height // 2 - half_h

    async def place_crosshair(self, fallback_width: int, fallback_height: int) -> list:
        """Write the crosshair for the current style and nudge at the screen center.

        The resolution comes from the manual override, else gamescope, else the
        frontend's fallback_width/height. Returns [width, height, source, mangoapp_restarted].
        """
        style = self.settings["style"]
        detected = self.get_gamescope_resolution()
        override = self.parse_resolution_mode(self.settings["resolution_mode"])
        if isinstance(override, tuple):
            resolution, source = override, "manual"
        elif detected is not None:
            resolution, source = detected, "gamescope"
        else:
            resolution, source = (int(fallback_width), int(fallback_height)), "fallback"
            decky.logger.warning(f"Using frontend fallback resolution {resolution}")

        width, height = resolution
        center_x, center_y = self.compute_offsets(style, width, height)
        self.current_offset_x = center_x + self.settings["nudge_x"]
        self.current_offset_y = center_y + self.settings["nudge_y"]
        # Write first: a restarted mangoapp reads the config on startup, and while
        # it is down the config path could not be looked up.
        await self.write_crosshair_config(*CROSSHAIR_TEXT[style], self.current_offset_x, self.current_offset_y)

        # The restart depends on the real display size, not on a manual override.
        restarted = False
        pid = self.find_mangoapp_pid()
        if detected is not None and pid is not None and self.mangoapp_resolution.get(pid) != detected:
            new_pid = await self.restart_mangoapp(pid)
            if new_pid is not None:
                self.mangoapp_resolution[new_pid] = detected
                restarted = True
        return [width, height, source, restarted]

    # ------------------------------------------------------------------ #
    # Methods called from the frontend
    # ------------------------------------------------------------------ #
    async def get_state(self) -> dict:
        return {
            **self.settings,
            "active": self.current_offset_x is not None,
            "offset_x": self.current_offset_x,
            "offset_y": self.current_offset_y,
        }

    async def make_crosshair(self, style: str, fallback_width: int, fallback_height: int) -> list:
        if style not in CROSSHAIR_TEXT:
            raise ValueError(f"Unknown crosshair style: {style}")
        self.settings["style"] = style
        self.save_settings()
        return await self.place_crosshair(fallback_width, fallback_height)

    async def recenter_crosshair(self, fallback_width: int, fallback_height: int) -> list:
        self.settings["nudge_x"] = 0
        self.settings["nudge_y"] = 0
        self.save_settings()
        return await self.place_crosshair(fallback_width, fallback_height)

    async def set_resolution_mode(self, mode: str, fallback_width: int, fallback_height: int):
        """Change the resolution override; re-places a visible crosshair. Returns
        the place_crosshair result, or None if no crosshair is shown."""
        if self.parse_resolution_mode(mode) is None:
            raise ValueError(f"Invalid resolution mode: {mode}")
        self.settings["resolution_mode"] = mode
        self.save_settings()
        if self.current_offset_x is None:
            return None
        return await self.place_crosshair(fallback_width, fallback_height)

    async def set_nudge_step(self, step: int):
        if step not in NUDGE_STEPS:
            raise ValueError(f"Invalid nudge step: {step}")
        self.settings["nudge_step"] = step
        self.save_settings()

    async def remove_crosshair(self):
        self.current_offset_x = None
        self.current_offset_y = None
        await self.write_crosshair_config("", "", "", 0, 0)

    async def adjust_crosshair_offset(self, x_delta: int, y_delta: int):
        """Move the crosshair; the correction is saved and kept for later placements."""
        self.settings["nudge_x"] += int(x_delta)
        self.settings["nudge_y"] += int(y_delta)
        self.save_settings()
        if self.current_offset_x is None:
            return
        self.current_offset_x += int(x_delta)
        self.current_offset_y += int(y_delta)
        await self.write_crosshair_config(
            *CROSSHAIR_TEXT[self.settings["style"]], self.current_offset_x, self.current_offset_y
        )

    async def _main(self):
        self.load_settings()
        decky.logger.info("Crosshair Plugin initialized!")

    async def _unload(self):
        decky.logger.info("Crosshair Plugin unloaded!")
