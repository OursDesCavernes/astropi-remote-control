import os
import subprocess
from typing import List, Dict


class SystemManager:
    def __init__(self):
        self._supported_commands: Dict[str, str] = {}
        shutdown_cmd = os.getenv('SHUTDOWN_CMD')
        restart_cmd = os.getenv('RESTART_CMD')
        if shutdown_cmd:
            self._supported_commands['shutdown'] = shutdown_cmd
        if restart_cmd:
            self._supported_commands['restart'] = restart_cmd

    def run_command(self, command: str):
        if command in self._supported_commands.keys():
            subprocess.run(self._supported_commands[command], check=True, shell=True)
        else:
            raise RuntimeError(f"Unsupported command: {command}")

    @property
    def supported_commands(self) -> List[str]:
        return [s for s in self._supported_commands.keys()]
