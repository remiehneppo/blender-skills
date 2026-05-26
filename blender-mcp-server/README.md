# blender-mcp-server

Local `stdio` MCP server for Blender 4.5 LTS+ automation and instance-mask image
editing. Blender work is run in isolated background processes; the MCP process
does not import `bpy`.

This package is licensed under `AGPL-3.0-or-later` because its optional
segmentation integration directly uses Ultralytics YOLO. The existing skill
documents at the repository root retain their stated license.

## Install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
# Install only when external-image segmentation is needed:
pip install -e '.[segmentation]'
```

Install Blender 4.5 LTS or newer separately. Download and cache a segmentation
weight explicitly; the server never downloads weights during a tool call.

## Configure

```bash
export BLENDER_BIN=/path/to/blender
export BLENDER_MCP_WORKSPACE_ROOT=/path/to/input-workspace
export BLENDER_MCP_OUTPUT_ROOT=/path/to/blender-artifacts
export BLENDER_MCP_YOLO_MODEL=/path/to/yolo11n-seg.pt
# Optional: export BLENDER_MCP_YOLO_DEVICE=cpu
blender-mcp
```

`BLENDER_MCP_WORKSPACE_ROOT` is the only accepted source for input assets.
`BLENDER_MCP_OUTPUT_ROOT` is the only location the server writes jobs, scene
versions, logs and artifacts.

Set `BLENDER_MCP_ENABLE_UNSAFE_PYTHON=1` only to register
`blender_run_python`. That tool executes arbitrary code with the Blender
process's permissions and clients should require approval for every call.

## Selection Boundary

Use `image_segment` and `image_edit_by_mask` for arbitrary external images.
Use `render_object_mask` for exact object or material masks in a Blender
render, through Cryptomatte. An inferred YOLO mask is not treated as an
identity mapping to a 3D object.
