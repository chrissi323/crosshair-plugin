import asyncio
import os
import re
import signal
import subprocess
import decky

# Half the rendered crosshair text size in pixels; the crosshair is placed at
# "screen center minus this" (see compute_offsets).
TEXT_HALF_SIZE = {"box": (22, 20), "dot": (9, 20)}
CROSSHAIR_TEXT = {"box": ("-----", "| + |", "-----"), "dot": (" ", "+", " ")}


class Plugin:
    def __init__(self):
        self.current_offset_x = None
        self.current_offset_y = None
        self.current_style = "box"  # Track current crosshair style: "box" or "dot"
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

    @staticmethod
    def compute_offsets(style: str, width: int, height: int):
        half_w, half_h = TEXT_HALF_SIZE[style]
        return width // 2 - half_w, height // 2 - half_h

    async def make_auto_crosshair(self, style: str, fallback_width: int, fallback_height: int) -> list:
        """Place the crosshair for the current gamescope resolution.

        fallback_width/height come from the frontend and are only used if
        gamescope can't be queried. Returns [width, height, source, mangoapp_restarted].
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
        # Write first: a restarted mangoapp reads the config on startup, and while
        # it is down the config path could not be looked up.
        await self.write_crosshair_config(*CROSSHAIR_TEXT[style], self.current_offset_x, self.current_offset_y)

        restarted = False
        pid = self.find_mangoapp_pid()
        if source == "gamescope" and pid is not None and self.mangoapp_resolution.get(pid) != resolution:
            new_pid = await self.restart_mangoapp(pid)
            if new_pid is not None:
                self.mangoapp_resolution[new_pid] = resolution
                restarted = True
        return [width, height, source, restarted]

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