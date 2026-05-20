---
name: blender-modifiers
description: >
  Blender modifier stack management and depsgraph bake for headless scripts.
  Covers adding and configuring non-destructive modifiers (Boolean, Remesh,
  Decimate, Solidify), version-safe property access with hasattr guards, and
  baking the evaluated modifier stack into an export-ready mesh via
  Object.evaluated_get and bpy.data.meshes.new_from_object.
  Use when building 3D print pipelines with CSG holes, mesh regularization,
  polygon-count reduction, or wall thickness; and when you need to export
  modifier-applied geometry without destructively applying the modifier stack.
compatibility: "Blender 2.93+. RemeshModifier.voxel_size and BooleanModifier.solver require hasattr guards for pre-3.0 builds."
license: MIT
allowed-tools: Bash
---

## Add a modifier

```python
mod = obj.modifiers.new("ModifierName", 'MODIFIER_TYPE')
```

`type` enum is required. Common types: `'BOOLEAN'`, `'REMESH'`, `'DECIMATE'`, `'SOLIDIFY'`, `'ARRAY'`, `'SUBSURF'`.

---

## Boolean — CSG holes, unions, cutouts

```python
mod = obj.modifiers.new("Hole", 'BOOLEAN')
mod.operation = 'DIFFERENCE'   # 'UNION' | 'INTERSECT' | 'DIFFERENCE'
mod.object    = cutter_obj     # the cutting mesh object
if hasattr(mod, "solver"):
    mod.solver = 'EXACT'       # 'EXACT' | 'FAST'  (version-dependent)
```

`mod.collection` accepts a collection instead of a single object (version-dependent exposure).

---

## Remesh — regularize topology

```python
mod = obj.modifiers.new("Remesh", 'REMESH')
if hasattr(mod, "mode"):
    try:    mod.mode = 'VOXEL'      # preferred in Blender 2.82+
    except: pass
if hasattr(mod, "voxel_size"):
    mod.voxel_size = 0.08           # smaller = denser
elif hasattr(mod, "octree_depth"):
    mod.octree_depth = 6            # older builds
```

---

## Decimate — reduce polygon count

```python
mod = obj.modifiers.new("LowPoly", 'DECIMATE')
if hasattr(mod, "ratio"):
    mod.ratio = 0.65                # 1.0 = no reduction, 0.0 = maximum
# For planar mode:
# mod.decimate_type = 'DISSOLVE'
# mod.angle_limit = math.radians(5)
```

---

## Solidify — add wall thickness

```python
mod = obj.modifiers.new("Wall", 'SOLIDIFY')
mod.thickness = 0.10
if hasattr(mod, "offset"):
    mod.offset = 0.0
if hasattr(mod, "use_even_offset"):
    mod.use_even_offset = True
```

---

## Depsgraph bake — export modifier-applied mesh

Bakes the full modifier stack into a standalone mesh **without** destructively applying modifiers. Use before export.

```python
depsgraph   = bpy.context.evaluated_depsgraph_get()
obj_eval    = obj.evaluated_get(depsgraph)
mesh_baked  = bpy.data.meshes.new_from_object(obj_eval)
obj_baked   = bpy.data.objects.new("Part_Final", mesh_baked)

# Replace scene with baked object so exporters operate on clean geometry
for old in list(bpy.data.objects):
    bpy.data.objects.remove(old, do_unlink=True)
bpy.context.scene.collection.objects.link(obj_baked)
```

`Object.to_mesh()` is an alternative for simple cases, but `new_from_object` is safer for modifier-heavy pipelines.

---

## hasattr guard pattern

Always guard version-sensitive properties:
```python
if hasattr(mod, "property_name"):
    mod.property_name = value
```
This keeps scripts runnable across Blender releases without hard failures.
