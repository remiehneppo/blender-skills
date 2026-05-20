---
name: blender-rendering
description: >
  Blender headless scene rendering to image files (PNG, JPEG, EXR).
  Covers camera and light datablock setup, render engine selection
  (BLENDER_EEVEE, CYCLES), resolution and output format configuration,
  bpy.ops.render.render for still and animation rendering, and batch
  multi-angle render loops.
  Use when generating product renders, previews, turntables, or any
  render-to-image pipeline from a background script.
  For compositor post-processing, see blender-compositing.
compatibility: "Blender 2.93+. EEVEE available in both legacy (BLENDER_EEVEE) and Next (BLENDER_EEVEE_NEXT, 4.2+) engines."
license: MIT
allowed-tools: Bash
---

## Camera setup

```python
import math, bpy

cam_data = bpy.data.cameras.new("Camera")
cam = bpy.data.objects.new("Camera", cam_data)
bpy.context.scene.collection.objects.link(cam)

cam.location       = (0.0, -5.0, 1.5)
cam.rotation_euler = (math.radians(75), 0.0, 0.0)   # (X, Y, Z) in radians

bpy.context.scene.camera = cam
```

Camera-specific settings: `cam_data.lens` (focal length mm), `cam_data.clip_start`, `cam_data.clip_end`, `cam_data.type = 'PERSP'|'ORTHO'|'PANO'`.

## Light setup

```python
light_data = bpy.data.lights.new(name="Sun", type='SUN')  # 'SUN'|'POINT'|'AREA'|'SPOT'
light = bpy.data.objects.new("Sun", light_data)
bpy.context.scene.collection.objects.link(light)
light.rotation_euler = (math.radians(50), 0.0, math.radians(25))
# light_data.energy = 5.0  # optional
```

## Render settings

```python
scene = bpy.context.scene

scene.render.engine          = 'BLENDER_EEVEE'   # or 'CYCLES'
scene.render.resolution_x    = 1024
scene.render.resolution_y    = 1024
scene.render.resolution_percentage = 100         # optional, default 100

scene.render.image_settings.file_format  = 'PNG'   # 'PNG'|'JPEG'|'OPEN_EXR'|'TIFF'
scene.render.image_settings.color_mode   = 'RGBA'  # 'BW'|'RGB'|'RGBA'
scene.render.image_settings.color_depth  = '8'     # '8'|'16' (PNG); '16'|'32' (EXR)
scene.render.image_settings.compression  = 15      # PNG compression 0-100

scene.render.filepath = "/path/to/output.png"
```

## Render still

```python
bpy.ops.render.render(write_still=True)
# Writes to scene.render.filepath
```

Parameters:
- `write_still=True` — saves to `filepath` (required for headless)
- `animation=False` — single frame (default)
- `use_viewport=False` — don't use viewport camera

## Render animation

```python
scene.frame_start = 1
scene.frame_end   = 24
bpy.ops.render.render(animation=True)
# Output: filepath with frame number padding, e.g. /path/render_0001.png
```

## Batch multi-angle renders

```python
for i, angle_deg in enumerate((0, 90, 180, 270), start=1):
    angle = math.radians(angle_deg)
    cam.location       = (4.0 * math.cos(angle), 4.0 * math.sin(angle), 2.0)
    cam.rotation_euler = (math.radians(63), 0.0, angle + math.radians(90))
    scene.render.filepath = f"/out/view_{i:02d}.png"
    bpy.ops.render.render(write_still=True)
```

## EEVEE vs CYCLES

| | BLENDER_EEVEE | CYCLES |
|---|---|---|
| Speed | Fast (real-time rasterizer) | Slow (path tracer) |
| Quality | Good for most previews | Photo-realistic |
| Headless | Fully supported | Fully supported |
| GPU config | `scene.eevee.*` | `scene.cycles.*`, `bpy.context.preferences.addons['cycles'].preferences` |

For CI/batch jobs, `BLENDER_EEVEE` is usually sufficient and significantly faster.
