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
# Optional: set the output root; defaults to the current working directory.
export BLENDER_MCP_OUTPUT_ROOT=/path/to/blender-artifacts
export BLENDER_MCP_YOLO_MODEL=/path/to/yolo11n-seg.pt
# Optional: enable Blender add-ons that your scenes or scripts rely on.
export BLENDER_MCP_BLENDER_ADDONS=add_mesh_extra_objects
# Optional: export BLENDER_MCP_YOLO_DEVICE=cpu
blender-mcp
```

`BLENDER_MCP_WORKSPACE_ROOT` is the only accepted source for input assets.
By default the server writes jobs, scene versions, logs and artifacts to the
current working directory. Set `BLENDER_MCP_OUTPUT_ROOT` to override that
location.

Set `BLENDER_MCP_ENABLE_UNSAFE_PYTHON=1` only to register
`blender_run_python`. That tool executes arbitrary code with the Blender
process's permissions and clients should require approval for every call.

### Gear scene note

Blender's `add_mesh_extra_objects` gear primitive uses a fixed reference where a
tooth points along `+Y` at zero spin. For planetary assemblies, keep the ring
fixed, drive the sun, and build each planet as `carrier -> arm -> planet` so
the orbit and tooth phase stay separate. Use the reference orientation offset
`90° - 180°/teeth` for external gear phase when the mesh needs to line up with
a mating gear.
For concentric same-plane assemblies, put the inner and outer rings on the same
`Z` plane and drive their carriers with opposite sign if the design needs
counter-rotation.
After any scene edit, render a preview image and review it once before marking
the change done.
Do not reuse near-identical orbit radii for adjacent same-plane gear rings; the
planet envelopes need visible radial separation or they will overlap.
When editing models, always inspect the rendered preview for overlaps, wrong
clearances, and non-meshing parts before you treat the result as finished.

## Selection Boundary

Use `image_segment` and `image_edit_by_mask` for arbitrary external images.
Use `render_object_mask` for exact object or material masks in a Blender
render, through Cryptomatte. An inferred YOLO mask is not treated as an
identity mapping to a 3D object.
