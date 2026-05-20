---
name: blender-image-editing
description: >
  Blender headless image datablock manipulation: load, create, read/write pixels,
  resize, and save images without rendering a 3D scene. Covers bpy.data.images.load,
  bpy.data.images.new, Image.pixels (flat RGBA buffer), Image.scale, Image.save,
  Image.save_render, render image_settings for format config, and
  bpy.app.handlers.render_complete for batch callback-driven multi-render sequences.
  Use when processing image files in batch (resize, color transform, format convert),
  generating procedural images programmatically, or orchestrating multi-shot renders
  with per-render callbacks.
  For compositor-based post-processing, see blender-compositing.
compatibility: "Blender 2.93+. Image.save() and Image.pixels API stable across 2.93–4.x."
license: MIT
allowed-tools: Bash
---

## Load an existing image

```python
img = bpy.data.images.load("/path/to/file.png", check_existing=True)
# check_existing=True: reuse if already loaded (avoids duplicates in batch loops)
```

## Create a generated image

```python
img = bpy.data.images.new(
    "Canvas",
    width=512,
    height=512,
    alpha=True,          # include alpha channel
    float_buffer=False,  # True for 32-bit float (HDR)
)
```

## Read and write pixels

Pixel buffer is a flat RGBA float list: `[R, G, B, A, R, G, B, A, ...]`
Length = `width * height * 4`. Values 0.0–1.0.

```python
# Read
px = list(img.pixels)

# Modify (invert RGB, keep alpha)
for i in range(0, len(px), 4):
    px[i]   = 1.0 - px[i]    # R
    px[i+1] = 1.0 - px[i+1]  # G
    px[i+2] = 1.0 - px[i+2]  # B
    # px[i+3] unchanged       # A

# Write back
img.pixels = px
```

Pixel coordinates: index `(y * width + x) * 4` for pixel at `(x, y)`.

## Resize

```python
img.scale(new_width, new_height)   # in-place resize
```

## Save

```python
# Method 1: direct save (uses image's own filepath/format settings)
img.filepath_raw = "/out/result.png"
img.file_format  = 'PNG'           # 'PNG'|'JPEG'|'TIFF'|'BMP'|'OPEN_EXR'
img.save()

# Method 2: save via render settings (respects scene.render.image_settings)
scene = bpy.context.scene
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode  = 'RGBA'
img.save_render("/out/result.png", scene=scene)
```

`save_render` applies render color management; `save` uses the image's own settings.

## Batch process files

```python
import glob, os, bpy

scene = bpy.context.scene
scene.render.image_settings.file_format = 'PNG'

for src_path in glob.glob("/input/*.png"):
    img = bpy.data.images.load(src_path, check_existing=False)
    img.scale(256, 256)

    px = list(img.pixels)
    for i in range(0, len(px), 4):
        px[i], px[i+1], px[i+2] = px[i+2], px[i+1], px[i]  # swap R and B
    img.pixels = px

    out_path = os.path.join("/output", os.path.basename(src_path))
    img.save_render(out_path, scene=scene)
    bpy.data.images.remove(img)   # free memory in long batch loops
    print("Wrote:", out_path)
```

## Render handlers for multi-shot sequences

```python
import bpy

def on_render_complete(scene_):
    print("Shot done:", scene_.render.filepath)

# Register
bpy.app.handlers.render_complete.clear()
bpy.app.handlers.render_complete.append(on_render_complete)

# Loop renders
for i, filepath in enumerate(["/out/a.png", "/out/b.png", "/out/c.png"], 1):
    bpy.context.scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)  # handler fires after each

# Clean up
bpy.app.handlers.render_complete.clear()
```

Other useful handlers: `bpy.app.handlers.render_write`, `bpy.app.handlers.frame_change_pre`.

## Create procedural gradient image

```python
img = bpy.data.images.new("Gradient", width=128, height=128, alpha=True)
pixels = []
for y in range(128):
    for x in range(128):
        pixels.extend([x/127.0, y/127.0, 0.2, 1.0])   # R, G, B, A
img.pixels = pixels
img.filepath_raw = "/out/gradient.png"
img.file_format  = 'PNG'
img.save()
```
