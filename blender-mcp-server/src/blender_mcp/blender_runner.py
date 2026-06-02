"""Executed by Blender, not imported by the MCP process."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import bpy

from blender_mcp.blender_runner_actions import HANDLERS, inspect_scene


def _load(payload):
    source = payload.get("source_scene")
    if source:
        bpy.ops.wm.open_mainfile(filepath=source)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)


def _disable_backup_versions():
    try:
        bpy.context.preferences.filepaths.save_version = 0
    except Exception:
        pass


def main():
    payload_path, response_path = [Path(value) for value in sys.argv[sys.argv.index("--") + 1 :]]
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        _disable_backup_versions()
        _load(payload)
        _disable_backup_versions()
        action = payload["action"]
        if action == "inspect":
            result = inspect_scene()
        else:
            action_result = HANDLERS[action](payload.get("params", {}))
            scene_result = inspect_scene()
            result = scene_result if action_result is None else {"scene": scene_result, **action_result}
            if payload.get("output_scene"):
                bpy.ops.wm.save_as_mainfile(filepath=payload["output_scene"])
        response_path.write_text(json.dumps({"ok": True, "result": result}), encoding="utf-8")
    except Exception as exc:
        response_path.write_text(
            json.dumps({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}), encoding="utf-8"
        )
        raise


if __name__ == "__main__":
    main()
