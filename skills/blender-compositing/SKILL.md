---
name: blender-compositing
description: >
  Blender headless compositor node tree setup for post-processing rendered images.
  Covers enabling compositing (scene.use_nodes, scene.render.use_compositing),
  creating and connecting compositor nodes (Nodes.new, NodeLinks.new), and
  configuring blur, rotate, translate, scale, alpha-over, and file-output nodes.
  Includes version-compatible patterns for CompositorNodeOutputFile directory field.
  Use when applying post-process effects to renders, compositing overlays, chaining
  image operations in a node graph, or writing compositor output directly to disk.
  For rendering the scene, see blender-rendering. For direct pixel edits, see blender-image-editing.
  See ../_shared/compat-matrix.md for compositor version-compat details.
compatibility: "Blender 2.93+. CompositorNodeOutputFile.base_path renamed to .directory in some builds; use hasattr guard."
license: MIT
allowed-tools: Bash
---

## Enable compositor

```python
scene = bpy.context.scene
scene.use_nodes = True                # harmless on all versions
scene.render.use_compositing = True   # authoritative current toggle; set both for broad compat

tree = scene.node_tree
# Clean existing nodes (start fresh)
for n in list(tree.nodes):
    tree.nodes.remove(n)
```

## Create and connect nodes

```python
# Create
rl   = tree.nodes.new("CompositorNodeRLayers")    # render layer source
blur = tree.nodes.new("CompositorNodeBlur")

# Connect sockets by name
tree.links.new(rl.outputs["Image"], blur.inputs["Image"])
```

`NodeLinks.new(from_socket, to_socket)` — both sockets required.
`handle_dynamic_sockets=False` optional param for dynamic socket types.

## Node reference

| Purpose | bl_idname | Key properties / inputs |
|---------|-----------|------------------------|
| Render layer source | `CompositorNodeRLayers` | outputs: `"Image"`, `"Alpha"` |
| External image source | `CompositorNodeImage` | `node.image = img_datablock` |
| Blur | `CompositorNodeBlur` | `size_x`, `size_y`, `filter_type` (enum); inputs: `"Image"`, `"Size"` |
| Rotate | `CompositorNodeRotate` | `filter_type: 'NEAREST'|'BILINEAR'|'BICUBIC'`; input socket `"Angle"` (radians) |
| Translate | `CompositorNodeTranslate` | input sockets `"X"`, `"Y"` (pixels) |
| Scale | `CompositorNodeScale` | `frame_method: 'STRETCH'|'FIT'|'CROP'`; `space` enum |
| Alpha Over | `CompositorNodeAlphaOver` | `use_premultiply`; input `"Fac"` for factor |
| File Output | `CompositorNodeOutputFile` | see version compat below |
| Composite output | `CompositorNodeComposite` | final output — pairs with `render(write_still=True)` |

## Set node properties and socket inputs

```python
# Properties on the node
if hasattr(blur, "size_x"):  blur.size_x = 8
if hasattr(blur, "size_y"):  blur.size_y = 8
if hasattr(rot, "filter_type"):  rot.filter_type = 'BILINEAR'

# Socket-driven values
if "Angle" in rot.inputs:   rot.inputs["Angle"].default_value = math.radians(4.0)
if "X" in trn.inputs:       trn.inputs["X"].default_value = 24.0
if "Y" in trn.inputs:       trn.inputs["Y"].default_value = -18.0
```

## File Output node — version compat

```python
fout = tree.nodes.new("CompositorNodeOutputFile")

# Directory field changed between versions:
if hasattr(fout, "base_path"):
    fout.base_path = outdir      # older Blender
elif hasattr(fout, "directory"):
    fout.directory = outdir      # current Blender

# Connect to first input slot (safe cross-version)
tree.links.new(last_node.outputs["Image"], fout.inputs[0])
```

Avoid multi-output socket creation unless needed — the default slot is stable across versions.

## Minimal post-process pipeline

```python
import math, bpy

scene = bpy.context.scene
scene.use_nodes = True
scene.render.use_compositing = True
tree = scene.node_tree
for n in list(tree.nodes): tree.nodes.remove(n)

rl   = tree.nodes.new("CompositorNodeRLayers")
blur = tree.nodes.new("CompositorNodeBlur")
comp = tree.nodes.new("CompositorNodeComposite")

if hasattr(blur, "size_x"): blur.size_x = 4
if hasattr(blur, "size_y"): blur.size_y = 4

tree.links.new(rl.outputs["Image"],   blur.inputs["Image"])
tree.links.new(blur.outputs["Image"], comp.inputs["Image"])

bpy.ops.render.render(write_still=True)   # compositor runs automatically
```
