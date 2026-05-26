# Blender API Compatibility Matrix

Headless script version-compat reference. Use `hasattr()` or try/except for all entries marked version-sensitive.

## Exporter operator names

| Format | Current operator (Blender 4.0+) | Legacy operator (pre-4.0) | Notes |
|--------|--------------------------------|--------------------------|-------|
| OBJ export | `bpy.ops.wm.obj_export` | `bpy.ops.export_scene.obj` | Probe current first, fallback second |
| OBJ import | `bpy.ops.wm.obj_import` | `bpy.ops.import_scene.obj` | Same pattern |
| STL export | `bpy.ops.wm.stl_export` | `bpy.ops.export_mesh.stl` | Probe current first, fallback second |
| STL import | `bpy.ops.wm.stl_import` | `bpy.ops.import_mesh.stl` | Same pattern |
| glTF/GLB import/export | `bpy.ops.import_scene.gltf` / `bpy.ops.export_scene.gltf` | N/A | Core add-on available in Blender 4.5 LTS |
| FBX import/export | `bpy.ops.import_scene.fbx` / `bpy.ops.export_scene.fbx` | N/A | Core add-on available in Blender 4.5 LTS |
| USD import/export | `bpy.ops.wm.usd_import` / `bpy.ops.wm.usd_export` | N/A | Built into Blender 4.5 LTS |
| 3MF export | `bpy.ops.export_mesh.threemf` | N/A | Add-on/extension required; load with `--addons` |
| AMF export | add-on defined — probe `bpy.ops.export_mesh.amf` then `bpy.ops.wm.amf_export` | N/A | Not in core; treat as optional |

### Probe pattern (OBJ example)
```python
try:
    bpy.ops.wm.obj_export(filepath=path, apply_modifiers=True, export_selected_objects=False)
except Exception:
    bpy.ops.export_scene.obj(filepath=path, use_selection=False, use_mesh_modifiers=True)
```

### AMF probe pattern
```python
amf_done = False
for module, op, kwargs in [
    ("export_mesh", "amf",    {"filepath": path}),
    ("wm",          "amf_export", {"filepath": path}),
]:
    try:
        op_mod = getattr(bpy.ops, module)
        if op in dir(op_mod):
            getattr(op_mod, op)(**kwargs)
            amf_done = True
            break
    except Exception as e:
        print(f"AMF attempt {module}.{op} failed:", e)
if not amf_done:
    print("No AMF operator found. Install an AMF add-on.")
```

---

## Compositor

| Feature | Current pattern | Older pattern | Notes |
|---------|----------------|---------------|-------|
| Enable compositing | `scene.render.use_compositing = True` | `scene.use_nodes = True` | Set both for broad coverage |
| Access node tree | `tree = scene.node_tree` | same | Unchanged |
| File Output: output directory | `fout.directory = outdir` | `fout.base_path = outdir` | Use `hasattr` check |
| File Output: multi-output sockets | `file_output_items` (Blender 5.0+ notes) | `file_slots` (older) | Default input slot is safest cross-version |

### Compositor enable pattern
```python
scene.use_nodes = True                # harmless on all versions
scene.render.use_compositing = True   # authoritative current toggle
tree = scene.node_tree
```

### File Output directory compat
```python
if hasattr(fout, "base_path"):
    fout.base_path = outdir
elif hasattr(fout, "directory"):
    fout.directory = outdir
```

### Cryptomatte masks for known scenes

For Blender renders where object or material identity is known, enable
`view_layer.use_pass_cryptomatte_object` or
`view_layer.use_pass_cryptomatte_material` and use
`CompositorNodeCryptomatteV2`. In Blender 4.5, the node layer value includes
the view layer prefix, for example `ViewLayer.CryptoObject`. This is more
precise than running a detector on the finished render.

---

## Modifier properties (version-sensitive)

| Modifier | Property | Guard |
|----------|----------|-------|
| RemeshModifier | `mode = 'VOXEL'` | `try/except` |
| RemeshModifier | `voxel_size` | `hasattr(mod, "voxel_size")` |
| RemeshModifier | `octree_depth` | `hasattr(mod, "octree_depth")` — fallback for older |
| BooleanModifier | `solver = 'EXACT'` | `hasattr(mod, "solver")` |
| SolidifyModifier | `offset` | `hasattr(mod, "offset")` |

---

## BMesh ops

| Op | Version note |
|----|-------------|
| `bmesh.ops.recalc_face_normals` | Guard: `if hasattr(bmesh.ops, 'recalc_face_normals')` |
| `bmesh.ops.remove_doubles` | Stable across current versions |
| `bmesh.ops.holes_fill` | Stable — boundary edge detection: `[e for e in bm.edges if e.is_boundary]` |
