---
name: blender-mesh-repair
description: >
  Blender headless mesh repair pipeline for 3D printing and watertight geometry.
  Covers Mesh.validate to detect and auto-fix invalid geometry, BMesh operations
  for welding duplicate vertices (remove_doubles), filling open holes (holes_fill),
  triangulating faces (triangulate), and recomputing face normals (version-guarded).
  Use when preparing meshes for print export, after Boolean operations, after
  from_pydata construction, or whenever non-manifold or degenerate geometry is suspected.
compatibility: "Blender 2.93+. bmesh.ops.recalc_face_normals requires hasattr guard on some 2.x builds."
license: MIT
allowed-tools: Bash
---

## When to repair

- After `from_pydata` (may have duplicates)
- After Boolean modifier bake (may leave non-manifold edges)
- Before print export (STL/OBJ/3MF slicers require manifold geometry)
- After any import from external source

## Full repair workflow

```python
import bmesh

def repair_mesh(mesh):
    """Weld duplicates, fill holes, triangulate, recompute normals."""

    # Step 1: validate before (returns True if invalid geo was found)
    print("validate before:", mesh.validate(verbose=False))

    bm = bmesh.new()
    bm.from_mesh(mesh)

    # Step 2: weld nearly coincident vertices
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)

    # Step 3: fill open boundary loops
    boundary_edges = [e for e in bm.edges if e.is_boundary]
    if boundary_edges:
        bmesh.ops.holes_fill(bm, edges=boundary_edges, sides=0)

    # Step 4: triangulate for deterministic export topology
    bmesh.ops.triangulate(bm, faces=bm.faces[:])

    # Step 5: recompute normals (version-guarded)
    if hasattr(bmesh.ops, "recalc_face_normals"):
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    bm.to_mesh(mesh)
    mesh.update()
    bm.free()

    # Step 6: validate after
    print("validate after:", mesh.validate(verbose=False))
```

## API reference

### `Mesh.validate`
```python
changed = mesh.validate(verbose=False, clean_customdata=True)
# Returns True when invalid geometry was corrected or removed.
# verbose=True prints details to stdout.
```

### `bmesh.ops.remove_doubles`
```python
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
# dist: merge threshold in Blender units. 1e-5 to 1e-6 typical for print work.
```

### `bmesh.ops.holes_fill`
```python
boundary_edges = [e for e in bm.edges if e.is_boundary]
bmesh.ops.holes_fill(bm, edges=boundary_edges, sides=0)
# sides=0 means fill regardless of hole vertex count.
# Only fills edges that are boundary (connected to exactly one face).
```

### `bmesh.ops.triangulate`
```python
bmesh.ops.triangulate(
    bm,
    faces=bm.faces[:],
    quad_method='BEAUTY',     # optional: 'BEAUTY' | 'FIXED' | 'FIXED_ALTERNATE' | 'SHORTEST_DIAGONAL'
    ngon_method='EAR_CLIP',   # optional: 'BEAUTY' | 'EAR_CLIP'
)
```

### `bmesh.ops.recalc_face_normals` (version-guarded)
```python
if hasattr(bmesh.ops, "recalc_face_normals"):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
```

## Non-manifold detection

```python
non_manifold_verts = [v for v in bm.verts if not v.is_manifold]
non_manifold_edges = [e for e in bm.edges if not e.is_manifold]
print(f"Non-manifold: {len(non_manifold_verts)} verts, {len(non_manifold_edges)} edges")
```
