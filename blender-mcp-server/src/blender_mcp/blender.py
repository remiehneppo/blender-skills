from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import Settings
from .jobs import JobStore


class BlenderExecutionError(RuntimeError):
    pass


class BlenderExecutor:
    def __init__(self, settings: Settings, store: JobStore):
        self.settings = settings
        self.store = store
        self.runner = Path(__file__).with_name("blender_runner.py")

    def _blender_command(self, *extra: str) -> list[str]:
        command = [
            str(self.settings.blender_bin),
            "--background",
            "--factory-startup",
        ]
        if self.settings.blender_addons:
            command.extend(["--addons", ",".join(self.settings.blender_addons)])
        command.extend(extra)
        return command

    def healthcheck(self) -> dict[str, Any]:
        response: dict[str, Any] = {
            "blender_bin": str(self.settings.blender_bin),
            "blender_addons": list(self.settings.blender_addons),
            "blender_available": self.settings.blender_bin.is_file() and os.access(self.settings.blender_bin, os.X_OK),
            "output_root": str(self.store.paths.prepare_output_root()),
            "yolo_model": str(self.settings.yolo_model),
            "segmentation_device": self.settings.yolo_device or "ultralytics-default",
            "segmentation_model_available": self.settings.yolo_model.is_file(),
        }
        if response["blender_available"]:
            try:
                completed = subprocess.run(self._blender_command("--version"), capture_output=True, text=True, timeout=15, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                response["error"] = f"Unable to execute Blender healthcheck: {exc}"
                return response
            response["blender_version"] = (completed.stdout or completed.stderr).splitlines()[0]
            match = re.search(r"Blender\s+(\d+)\.(\d+)", response["blender_version"])
            response["blender_compatible"] = bool(match and tuple(map(int, match.groups())) >= (4, 5))
            try:
                runner = subprocess.run(
                    self._blender_command("--python-expr", "import bpy; print('BLENDER_MCP_PYTHON_OK')"),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                response["python_runner_available"] = False
                response["error"] = f"Blender failed to execute a background bpy healthcheck: {exc}"
                return response
            response["python_runner_available"] = (
                runner.returncode == 0 and "BLENDER_MCP_PYTHON_OK" in runner.stdout
            )
            if not response["python_runner_available"]:
                response["error"] = "Blender was found but failed to execute a background bpy healthcheck."
        else:
            response["error"] = "BLENDER_BIN does not point to an executable file; install Blender 4.5 LTS+."
        return response

    def run(
        self,
        job_id: str,
        action: str,
        params: dict[str, Any],
        *,
        mutate_scene: bool = True,
        timeout: float | None = None,
        source_scene: Path | None = None,
    ) -> dict[str, Any]:
        source = source_scene or self.store.current_scene(job_id)
        candidate = self.store.candidate_scene(job_id) if mutate_scene else None
        directory = self.store.directory(job_id)
        log_path = directory / "logs" / f"{action}_{len(self.store.load(job_id)['operations']) + 1:04d}.log"
        with tempfile.TemporaryDirectory() as temporary:
            payload_path = Path(temporary) / "payload.json"
            response_path = Path(temporary) / "response.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "action": action,
                        "source_scene": str(source) if source else None,
                        "output_scene": str(candidate) if candidate else None,
                        "params": params,
                    }
                ),
                encoding="utf-8",
            )
            try:
                completed = subprocess.run(
                    self._blender_command(
                        "--python",
                        str(self.runner),
                        "--",
                        str(payload_path),
                        str(response_path),
                    ),
                    capture_output=True,
                    text=True,
                    timeout=timeout or self.settings.default_timeout,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                if candidate and candidate.exists():
                    candidate.unlink()
                self.store.record_failure(job_id, action, str(exc))
                raise BlenderExecutionError(str(exc)) from exc
            log_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
            response = json.loads(response_path.read_text(encoding="utf-8")) if response_path.exists() else {}
            if completed.returncode != 0 or not response.get("ok"):
                message = response.get("error", f"Blender exited with code {completed.returncode}")
                if candidate and candidate.exists():
                    candidate.unlink()
                self.store.record_failure(job_id, action, message)
                raise BlenderExecutionError(message)
            if candidate:
                self.store.commit_scene(job_id, candidate, action)
            else:
                self.store.record_success(job_id, action)
            return response["result"]
