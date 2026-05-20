---
name: blender-3d-export
description: >
  Blender headless 3D mesh export for STL, OBJ, 3MF, and AMF formats with
  version-compatible fallbacks. Covers the current wm.obj_export / wm.stl_export
  operators (Blender 4.0+), legacy export_scene.obj / export_mesh.stl fallbacks,
  3MF via the threemf add-on, and AMF via operator probing.
  Use when exporting geometry to print-ready or CAD-exchange formats from
  background scripts, CI pipelines, or render farms.
  See ../_shared/compat-matrix.md for the full version-compat table.
compatibility: "Blender 2.93+. wm.obj_export / wm.stl_export added in 4.0; legacy operators used as fallback. 3MF requires io_scene_3mf add-on. AMF operator names vary by build."
license: MIT
allowed-tools: Bash
---

## Probe pattern (always use: current first, legacy fallback)

Operator names changed in Blender 4.0. Safe pattern for any version:

```python
try:
    <current_operator>(...)
except Exception:
    <legacy_operator>(...)
```

---

## OBJ export

```python
try:
    bpy.ops.wm.obj_export(
        filepath=path,
        apply_modifiers=True,
        export_selected_objects=False,
        global_scale=1.0,
        # forward_axis='NEGATIVE_Z', up_axis='Y'  # optional axis overrides
    )
except Exception:
    bpy.ops.export_scene.obj(
        filepath=path,
        use_selection=False,
        use_mesh_modifiers=True,
        global_scale=1.0,
    )
```

---

## STL export

```python
try:
    bpy.ops.wm.stl_export(
        filepath=path,
        # export_selected_objects=False,  # available on some versions
        global_scale=1.0,
    )
except Exception:
    bpy.ops.export_mesh.stl(
        filepath=path,
        use_selection=False,
        use_mesh_modifiers=True,
        global_scale=1.0,
        # use_ascii=False,  # binary STL (default)
    )
```

---

## 3MF export (add-on required)

Load the add-on before running the script:
```bash
blender --background --factory-startup --addons io_mesh_3mf --python job.py
```

Or enable in script: `bpy.ops.preferences.addon_enable(module="io_mesh_3mf")`

```python
try:
    bpy.ops.export_mesh.threemf(
        filepath=path,
        use_selection=False,
        global_scale=1.0,
    )
    print("3MF export succeeded.")
except Exception as e:
    print("3MF exporter unavailable:", e)
```

---

## AMF export (add-on defined — probe multiple operator names)

No stable core AMF operator. Probe known add-on operator names:

```python
amf_done = False
candidates = [
    ("export_mesh", "amf",        {"filepath": path}),
    ("wm",          "amf_export", {"filepath": path}),
]
for module, op, kwargs in candidates:
    try:
        op_mod = getattr(bpy.ops, module)
        if op in dir(op_mod):
            getattr(op_mod, op)(**kwargs)
            amf_done = True
            print(f"AMF export succeeded via bpy.ops.{module}.{op}")
            break
    except Exception as e:
        print(f"AMF attempt {module}.{op} failed:", e)

if not amf_done:
    print("No AMF operator found. Install an AMF add-on and rerun with --addons <module>.")
```

---

## Export all: depsgraph-baked object

Before exporting, ensure modifiers are baked:

```python
depsgraph  = bpy.context.evaluated_depsgraph_get()
obj_eval   = obj.evaluated_get(depsgraph)
mesh_baked = bpy.data.meshes.new_from_object(obj_eval)
obj_baked  = bpy.data.objects.new("Part_Final", mesh_baked)

for old in list(bpy.data.objects):
    bpy.data.objects.remove(old, do_unlink=True)
bpy.context.scene.collection.objects.link(obj_baked)

# Now run any export operator — it will see only the clean baked mesh
```

---

## Common export parameters

| Param | OBJ current | OBJ legacy | STL current | STL legacy |
|-------|-------------|------------|-------------|------------|
| Output path | `filepath` | `filepath` | `filepath` | `filepath` |
| Apply modifiers | `apply_modifiers` | `use_mesh_modifiers` | (baked externally) | `use_mesh_modifiers` |
| All objects | `export_selected_objects=False` | `use_selection=False` | — | `use_selection=False` |
| Scale | `global_scale` | `global_scale` | `global_scale` | `global_scale` |

See `../_shared/compat-matrix.md` for the full version compat table.
