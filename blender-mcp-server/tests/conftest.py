from __future__ import annotations

from pathlib import Path

import pytest

from blender_mcp.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    output = tmp_path / "output"
    workspace.mkdir()
    return Settings(
        blender_bin=Path("/nonexistent/blender"),
        workspace_root=workspace,
        output_root=output,
        yolo_model=tmp_path / "models" / "yolo11n-seg.pt",
    )
