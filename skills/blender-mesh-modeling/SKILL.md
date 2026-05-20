---
name: blender-mesh-modeling
description: >
  Blender headless geometry creation and BMesh topology editing.
  Covers creating mesh datablocks from Python data (bpy.data.meshes.new,
  Mesh.from_pydata), wrapping meshes in objects and linking to scenes,
  and editing topology with BMesh (extrude_face_region, translate, triangulate).
  Use when creating procedural geometry, building meshes from vertex/face lists,
  or editing mesh topology in a background script without a GUI.
  For modifiers and depsgraph bake, see blender-modifiers.
  For repair (remove_doubles, holes_fill), see blender-mesh-repair.
compatibility: "Requires Blender 2.93+ with bmesh module (included). BMesh API stable across 2.93–4.x."
license: MIT
allowed-tools: Bash
---

## Create mesh from Python data

```python
import bpy, bmesh

# 1. Create mesh datablock
mesh = bpy.data.meshes.new("PartMesh")

# 2. Fill with vertex/edge/face data
verts = [(-1,-1,0), (1,-1,0), (1,1,0), (-1,1,0),
         (-1,-1,2), (1,-1,2), (1,1,2), (-1,1,2)]
faces = [(0,1,2,3), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
mesh.from_pydata(verts, [], faces)   # edges=[] lets Blender derive them from faces
mesh.update()

# 3. Wrap in object and link to scene
obj = bpy.data.objects.new("PartObj", mesh)
bpy.context.scene.collection.objects.link(obj)
```

`from_pydata` params:
- `vertices` — required, sequence of `(x, y, z)` tuples
- `edges` — list of `(i, j)` index pairs; pass `[]` when faces fully define connectivity
- `faces` — list of index sequences (tris, quads, or ngons)

## BMesh workflow

```python
bm = bmesh.new()
bm.from_mesh(mesh)      # load from existing mesh datablock

# ... topology edits (see ops below) ...

bm.to_mesh(mesh)        # write back
mesh.update()
bm.free()               # release memory
```

Always call `bm.free()` when done. Mode switches invalidate references — avoid in headless scripts.

## BMesh operations

### Extrude faces

```python
top_faces = [f for f in bm.faces if f.calc_center_median().z > threshold]
ret = bmesh.ops.extrude_face_region(bm, geom=top_faces)
extruded_verts = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
bmesh.ops.translate(bm, verts=extruded_verts, vec=(0.0, 0.0, 1.0))
```

| Op | Required params | Notes |
|----|----------------|-------|
| `bmesh.ops.extrude_face_region` | `bm`, `geom` (faces/edges/verts) | Returns `{"geom": [new elements]}` |
| `bmesh.ops.translate` | `bm`, `verts`, `vec=(x,y,z)` | Object-local coordinates |
| `bmesh.ops.triangulate` | `bm`, `faces` | `quad_method`, `ngon_method` optional |
| `bmesh.ops.remove_doubles` | `bm`, `verts`, `dist` | See blender-mesh-repair |
| `bmesh.ops.holes_fill` | `bm`, `edges`, `sides=0` | See blender-mesh-repair |

### Triangulate all faces

```python
bmesh.ops.triangulate(bm, faces=bm.faces[:])
# Optional: quad_method='BEAUTY', ngon_method='EAR_CLIP'
```

### Filter geometry by position

```python
top_faces   = [f for f in bm.faces if f.calc_center_median().z > 1.0]
outer_verts = [v for v in bm.verts if v.co.x > 0.5]
```

## Ensure updates propagate

After `bm.to_mesh(mesh)`:
```python
mesh.update()
# If normals need recalculating:
mesh.calc_normals()   # or use bmesh.ops.recalc_face_normals before to_mesh
```

## Add primitive shortcut (operator-based)

When you don't need full procedural control, primitives are fine in headless:
```python
bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0,0,0))
obj = bpy.context.active_object
```
Other: `primitive_uv_sphere_add`, `primitive_cylinder_add`, `primitive_torus_add`, `primitive_monkey_add`.
