---
name: blender-headless
description: >
  Blender headless execution fundamentals for background automation scripts.
  Covers CLI invocation (--background, --factory-startup, --python, --addons),
  sys.argv argument parsing, scene bootstrapping, namespace overview (bpy.data,
  bpy.ops, bpy.types, bpy.context, bpy.props, bpy.app.handlers), and operator
  safety rules (poll() failures, Context.temp_override, why to prefer BMesh
  and datablock APIs over edit-mode operator chains).
  Use when writing any Blender script intended for background/headless execution,
  CI pipelines, render farms, or batch automation.
compatibility: "Requires Blender 2.93+ in PATH as `blender`. All patterns tested on 2.93–4.x."
license: MIT
allowed-tools: Bash, mcp__blender__*
---

## Preferred MCP Workflow

When `blender-mcp-server` is configured, start with `blender_healthcheck`,
then use `job_create` and `job_inspect`. Prefer its typed tools and versioned
scene artifacts over generating a standalone background script. Use raw Python
only through `blender_run_python` after explicit opt-in and per-call approval.

## CLI invocation

```bash
blender --background --factory-startup --addons <module_name> --python job.py -- arg1 arg2
```

- `--background` — no GUI
- `--factory-startup` — ignore user preferences/startup file (important for reproducibility)
- `--addons <module>` — enable add-on before script runs (use for 3MF, AMF, custom tools)
- `--python job.py` — execute script
- `--` — everything after this is available to Python via `sys.argv`

## Argument parsing

```python
import sys
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
# argv[0], argv[1], ... are your custom args
```

## Bootstrapping skeleton

```python
import os, sys, bpy, bmesh

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
outdir = os.path.abspath(argv[0] if argv else "./out")
os.makedirs(outdir, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)   # empty scene, no default cube
scene = bpy.context.scene
```

## Namespace quick-ref

| Namespace | Purpose |
|-----------|---------|
| `bpy.data` | All datablocks (meshes, objects, images, cameras, materials…) |
| `bpy.types` | RNA class definitions; use for `isinstance` checks and operator subclassing |
| `bpy.context` | Runtime context (active scene, object, area…) |
| `bpy.ops` | Operators — prefer datablock APIs first; use operators when no datablock equivalent |
| `bpy.props` | Typed property definitions for custom operators/add-ons |
| `bpy.app.handlers` | Callback lists (render_complete, render_write, frame_change…) |

## Operator safety

Many operators have a `poll()` test — they fail silently or raise RuntimeError in background mode if context is wrong (wrong area type, object not active, wrong mode).

**Rule:** prefer `bpy.data` + `bmesh` APIs over `bpy.ops` for geometry work. Use operators for things with no datablock equivalent (render, export, factory reset).

When an operator is unavoidable, use `Context.temp_override`:

```python
with bpy.context.temp_override(active_object=obj, selected_objects=[obj]):
    bpy.ops.object.some_operator()
```

Note: not every operator is fully override-friendly — test in your target Blender version.

## Custom operator skeleton (for reusable add-ons)

```python
import bpy

class WM_OT_headless_job(bpy.types.Operator):
    bl_idname = "wm.headless_job"
    bl_label  = "Headless Job"

    outdir: bpy.props.StringProperty(name="Output Directory", subtype='DIR_PATH')
    ratio:  bpy.props.FloatProperty(name="Decimate Ratio", default=0.5, min=0.0, max=1.0)

    def execute(self, context):
        # your logic here
        return {'FINISHED'}

def register():   bpy.utils.register_class(WM_OT_headless_job)
def unregister(): bpy.utils.unregister_class(WM_OT_headless_job)
```

## Mode-switch warning

`mode_set()` calls can reallocate mesh data and invalidate existing Python references.
In headless scripts: do all BMesh edits without mode switches, reacquire references after any unavoidable `mode_set()`.
