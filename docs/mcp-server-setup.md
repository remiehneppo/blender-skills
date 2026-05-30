# Blender MCP Server Setup

The local server in `blender-mcp-server/` uses MCP `stdio`. It writes protocol
traffic only on stdout; Blender process output is captured in each job's
`logs/` directory.

## Install

Use Blender 4.5 LTS or newer:

```bash
cd blender-mcp-server
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
```

For segmentation of external images, install the optional integration and
prepare model weights before starting the server:

```bash
pip install -e '.[segmentation]'
# Put an explicitly obtained yolo11n-seg.pt at a stable local path.
```

The server does not download weights on the first `image_segment` call.
Ultralytics integration and weights have AGPL/commercial licensing
requirements; `blender-mcp-server` is marked `AGPL-3.0-or-later`.

## Environment

```bash
export BLENDER_BIN=/absolute/path/to/blender
export BLENDER_MCP_WORKSPACE_ROOT=/absolute/path/to/readable-inputs
export BLENDER_MCP_OUTPUT_ROOT=/absolute/path/to/generated-artifacts
export BLENDER_MCP_YOLO_MODEL=/absolute/path/to/yolo11n-seg.pt
# Optional: comma-separated Blender add-ons to enable for every subprocess.
export BLENDER_MCP_BLENDER_ADDONS=add_mesh_extra_objects
# Optional Ultralytics device selector, for example cpu or 0:
export BLENDER_MCP_YOLO_DEVICE=cpu
```

Input scene, asset, texture and image paths must be inside
`BLENDER_MCP_WORKSPACE_ROOT`. The server creates job manifests, logs, versioned `.blend` scenes, renders,
exports and masks in the current working directory by default. Set
`BLENDER_MCP_OUTPUT_ROOT` to override that location.

Scene workflow rule: after any model edit, render a preview image and review it
before marking the task done. Check for object overlap, wrong spacing and
parts that should mesh but do not.

## Client Configuration

### Codex

Add a local stdio server in `~/.codex/config.toml` or project
`.codex/config.toml`:

```toml
[mcp_servers.blender]
command = "/absolute/path/blender-skills/blender-mcp-server/.venv/bin/blender-mcp"

[mcp_servers.blender.env]
BLENDER_BIN = "/absolute/path/to/blender"
BLENDER_MCP_WORKSPACE_ROOT = "/absolute/path/to/inputs"
BLENDER_MCP_OUTPUT_ROOT = "/absolute/path/to/outputs"
BLENDER_MCP_YOLO_MODEL = "/absolute/path/to/yolo11n-seg.pt"
BLENDER_MCP_BLENDER_ADDONS = "add_mesh_extra_objects"
```

### Claude Code

```bash
claude mcp add --transport stdio \
  --env BLENDER_BIN=/absolute/path/to/blender \
  --env BLENDER_MCP_WORKSPACE_ROOT=/absolute/path/to/inputs \
  --env BLENDER_MCP_OUTPUT_ROOT=/absolute/path/to/outputs \
  --env BLENDER_MCP_YOLO_MODEL=/absolute/path/to/yolo11n-seg.pt \
  --env BLENDER_MCP_BLENDER_ADDONS=add_mesh_extra_objects \
  blender -- /absolute/path/blender-skills/blender-mcp-server/.venv/bin/blender-mcp
```

### GitHub Copilot in VS Code

Create `.vscode/mcp.json`:

```json
{
  "servers": {
    "blender": {
      "type": "stdio",
      "command": "/absolute/path/blender-skills/blender-mcp-server/.venv/bin/blender-mcp",
      "args": [],
      "env": {
        "BLENDER_BIN": "/absolute/path/to/blender",
        "BLENDER_MCP_WORKSPACE_ROOT": "/absolute/path/to/inputs",
        "BLENDER_MCP_OUTPUT_ROOT": "/absolute/path/to/outputs",
        "BLENDER_MCP_YOLO_MODEL": "/absolute/path/to/yolo11n-seg.pt",
        "BLENDER_MCP_BLENDER_ADDONS": "add_mesh_extra_objects"
      }
    }
  }
}
```

Start by calling `blender_healthcheck` from each client.

## Unsafe Python

`blender_run_python` is absent by default. To register it, explicitly add:

```bash
export BLENDER_MCP_ENABLE_UNSAFE_PYTHON=1
```

Set the client approval policy to prompt on every `blender_run_python` call.
The tool executes arbitrary Python with the Blender process's privileges;
workspace and output-path checks cannot sandbox that code.

## Selection Rules

- For a render from a known Blender scene, use `render_object_mask`; it uses
  Cryptomatte object or material identity and preserves soft edges.
- For an external image, use `image_segment`, select one returned
  `instance_id`, then use `image_edit_by_mask`.
- An external YOLO mask is not a claim that a corresponding named 3D object
  exists without calibrated scene/camera data.

## Verification

```bash
cd blender-mcp-server
.venv/bin/pytest
```

The integration test exercises Blender healthcheck, scene versioning,
material/camera/render, modifier/repair, STL/GLB/USD export, Cryptomatte mask
output, compositor output and preservation of the last committed version after
a failed Blender operation.

## References

- [MCP Python server and stdio guidance](https://modelcontextprotocol.io/docs/develop/build-server)
- [Codex MCP configuration](https://developers.openai.com/codex/mcp)
- [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp)
- [GitHub Copilot MCP configuration](https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp-in-your-ide/extend-copilot-chat-with-mcp)
- [Ultralytics segmentation](https://docs.ultralytics.com/tasks/segment)
- [Ultralytics licensing](https://www.ultralytics.com/license)
- [Blender Cryptomatte manual](https://docs.blender.org/manual/en/latest/compositing/types/mask/cryptomatte.html)
