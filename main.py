import os
import re
import subprocess
import decky

# Known resolutions keep their hand-tuned offsets; anything else is computed
# as "screen center minus half the crosshair text size" (see compute_offsets).
PRESET_OFFSETS = {
    "box": {(1280, 800): (618, 380), (1920, 1080): (938, 520), (3840, 2160): (1900, 1060)},
    "dot": {(1280, 800): (631, 380), (1920, 1080): (952, 520), (3840, 2160): (1913, 1060)},
}
# Half the rendered text size in pixels, derived from the presets above.
TEXT_HALF_SIZE = {"box": (22, 20), "dot": (9, 20)}
CROSSHAIR_TEXT = {"box": ("-----", "| + |", "-----"), "dot": (" ", "+", " ")}


class Plugin:
    def __init__(self):
        self.current_offset_x = None
        self.current_offset_y = None
        self.current_style = "box"  # Track current crosshair style: "box" or "dot"

    def find_mangoapp_environ(self):
        """Return the environment of the running mangoapp process as a dict, or None"""
        for proc_dir in os.listdir("/proc"):
            if not proc_dir.isdigit():
                continue
            try:
                with open(f"/proc/{proc_dir}/cmdline", "r") as f:
                    cmdline = f.read()
                if "mangoapp" not in cmdline:
                    continue
                with open(f"/proc/{proc_dir}/environ", "r") as f:
                    environ = f.read()
                return dict(
                    var.split("=", 1) for var in environ.split("\0") if "=" in var
                )
            except (FileNotFoundError, PermissionError, IOError):
                # Skip processes we can't read
                continue
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

    @staticmethod
    def compute_offsets(style: str, width: int, height: int):
        preset = PRESET_OFFSETS[style].get((width, height))
        if preset:
            return preset
        half_w, half_h = TEXT_HALF_SIZE[style]
        return width // 2 - half_w, height // 2 - half_h

    async def make_auto_crosshair(self, style: str, fallback_width: int, fallback_height: int) -> list:
        """Place the crosshair for the current gamescope resolution.

        fallback_width/height come from the frontend and are only used if
        gamescope can't be queried. Returns [width, height, source].
        """
        if style not in CROSSHAIR_TEXT:
            raise ValueError(f"Unknown crosshair style: {style}")

        resolution = self.get_gamescope_resolution()
        source = "gamescope"
        if resolution is None:
            resolution = (int(fallback_width), int(fallback_height))
            source = "fallback"
            decky.logger.warning(f"Using frontend fallback resolution {resolution}")

        width, height = resolution
        self.current_offset_x, self.current_offset_y = self.compute_offsets(style, width, height)
        self.current_style = style
        await self.write_crosshair_config(*CROSSHAIR_TEXT[style], self.current_offset_x, self.current_offset_y)
        return [width, height, source]

    async def remove_crosshair(self):
        self.current_offset_x = 0
        self.current_offset_y = 0
        await self.write_crosshair_config("", "", "", self.current_offset_x, self.current_offset_y)

    async def adjust_crosshair_offset(self, x_delta: int, y_delta: int):
        if self.current_offset_x is None:
            self.current_offset_x = 640
        if self.current_offset_y is None:
            self.current_offset_y = 400

        self.current_offset_x += x_delta
        self.current_offset_y += y_delta

        await self.write_crosshair_config(*CROSSHAIR_TEXT[self.current_style], self.current_offset_x, self.current_offset_y)

    async def get_current_offsets(self) -> list:
        if self.current_offset_x is None:
            self.current_offset_x = 640
        if self.current_offset_y is None:
            self.current_offset_y = 400
        return [self.current_offset_x, self.current_offset_y]

    async def _main(self):
        decky.logger.info("Crosshair Plugin initialized!")

    async def _unload(self):
        decky.logger.info("Crosshair Plugin unloaded!")