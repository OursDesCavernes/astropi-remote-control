import re
import threading
from typing import Tuple, Dict, List, Optional

from commander import Commander


class CameraError(Exception): pass

class CameraReadError(CameraError): pass
class CameraWriteError(CameraError): pass
class CameraUnknownSettingError(CameraError): pass


def parse_value(text: str, key: str) -> Optional[str]:
    value_match = re.search(rf"{key}:\s*(.*)", text)
    value = value_match.group(1).strip() if value_match else None
    return value


class CameraManager:
    def __init__(self, commander: Commander):
        # --- Configuration Mapping ---
        class ConfigEntry:
            def __init__(self, path: str):
                self.path = path
                self.value: str = ""
                self.choices: List[str] = []

        # Maps simple names to the full gphoto2 config paths and stores data.
        self._config_map: Dict[str, ConfigEntry] = {
                    'shutter-speed': ConfigEntry(path='/main/capturesettings/shutterspeed'),
                    'iso': ConfigEntry(path='/main/imgsettings/iso'),
                    'aperture': ConfigEntry(path='/main/capturesettings/f-number'),
                    'manual-focus': ConfigEntry(path='/main/actions/manualfocus'),
                    'crop': ConfigEntry(path='/main/capturesettings/sensorcrop'),
                    'aspect-ratio': ConfigEntry(path='/main/capturesettings/aspectratio'),
                }
        self._commander = commander
        self._lock = threading.Lock()

    def apply_setting(self, setting: str, value: str) -> None:
        self._commander.execute_command(
            ["gphoto2", f"--set-config-value={self._config_map[setting].path}={value}"],
            startup_timeout=10,
            timeout=20
        )
        stdout, stderr, _ = self._commander.wait_for_outputs(timeout=20)
        if stderr and "error" in stderr.lower():
            raise CameraWriteError(stderr)
        if setting == "manual-focus":
            return
        self._config_map[setting].value = value


    def reload_camera(self):
        with self._lock:
            for k, v in self._config_map.items():
                self._commander.execute_command(
                    ["gphoto2", f"--get-config={v.path}"],
                    timeout=10,
                    startup_timeout=10,
                )
                stdout, stderr, _ = self._commander.wait_for_outputs(timeout=10)
                if not stdout or (stderr and "error" in stderr.lower()):
                    raise CameraReadError(stderr)

                value = parse_value(stdout, "Current")
                choice_type = parse_value(stdout, "Type")

                if choice_type == "RANGE":
                    bottom = parse_value(stdout, "Bottom")
                    top = parse_value(stdout, "Top")
                    step = parse_value(stdout, "Step")
                    if bottom is None or top is None or step is None:
                        raise CameraReadError(f"failed to parse range: bottom: {bottom}, top: {top}, step: {step}" )
                    choices = [{"value": str(i)} for i in range(int(bottom), int(top)+1, int(step))]
                elif choice_type == "RADIO":
                    choices_matches = re.findall(r"Choice:\s*\d+\s*(.*)", stdout)
                    choices = [{"value": m.strip()} for m in choices_matches]
                else:
                    raise CameraReadError(f"unsupported choice type: {choice_type}")

                if not choices:
                    raise CameraReadError()
                self._config_map[k].value = value
                self._config_map[k].choices = choices

    def read_setting(self,setting: str) -> Tuple[str, List[str]]:
        try:
            if self._config_map[setting].value == "":
                self.reload_camera()
            index = self._config_map[setting].value
            choices = self._config_map[setting].choices
            return index, choices
        except KeyError:
            raise CameraUnknownSettingError(f"Unknown setting: {setting}")
