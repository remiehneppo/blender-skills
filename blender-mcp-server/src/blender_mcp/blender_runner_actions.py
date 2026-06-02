"""Handler implementations executed by Blender."""

from __future__ import annotations

import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from blender_mcp.bbox import bbox_from_corners, bbox_intersects, bbox_minimum_translation, bbox_overlap
from blender_mcp.gear import gear_profile_points, gear_spec
from blender_mcp.joints import joint_profile_points, joint_spec


def _vector(value, default=(0.0, 0.0, 0.0)):
    return tuple(value if value is not None else default)


def _vector3(value, default=(0.0, 0.0, 0.0)):
    return tuple(float(component) for component in (value if value is not None else default))


def _object(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"Object not found: {name}")
    return obj


def _mesh_world_bbox(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    corners = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
    report = bbox_from_corners((corner.x, corner.y, corner.z) for corner in corners)
    report["corners"] = [[corner.x, corner.y, corner.z] for corner in corners]
    report["dimensions_mm"] = [dimension * 1000.0 for dimension in report["dimensions"]]
    report["center_mm"] = [coordinate * 1000.0 for coordinate in report["center"]]
    return report


def _mesh_payload(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    mesh.transform(evaluated.matrix_world)
    mesh.calc_loop_triangles()
    return evaluated, mesh


def _mesh_bvh(mesh):
    vertices = [vertex.co[:] for vertex in mesh.vertices]
    polygons = [tuple(loop_triangle.vertices) for loop_triangle in mesh.loop_triangles]
    return BVHTree.FromPolygons(vertices, polygons)


def _profile_mesh(name, profile, width):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm = bmesh.new()
    half_width = width / 2.0
    front = [bm.verts.new((x, y, -half_width)) for x, y in profile]
    back = [bm.verts.new((x, y, half_width)) for x, y in profile]
    bm.faces.new(front)
    bm.faces.new(list(reversed(back)))
    count = len(profile)
    for index in range(count):
        next_index = (index + 1) % count
        bm.faces.new([front[index], front[next_index], back[next_index], back[index]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _frame_matrix(anchor):
    location = Vector(_vector3(anchor.get("location")))
    normal = anchor.get("normal")
    up = anchor.get("up")
    if normal:
        z_axis = Vector(_vector3(normal))
        if z_axis.length == 0:
            z_axis = Vector((0.0, 0.0, 1.0))
        z_axis.normalize()
        if up:
            x_axis = Vector(_vector3(up)).cross(z_axis)
            if x_axis.length == 0:
                x_axis = Vector((1.0, 0.0, 0.0)).cross(z_axis)
        else:
            x_axis = Vector((1.0, 0.0, 0.0)).cross(z_axis)
            if x_axis.length == 0:
                x_axis = Vector((0.0, 1.0, 0.0)).cross(z_axis)
        x_axis.normalize()
        y_axis = z_axis.cross(x_axis)
        y_axis.normalize()
        return Matrix(
            (
                (x_axis.x, y_axis.x, z_axis.x, location.x),
                (x_axis.y, y_axis.y, z_axis.y, location.y),
                (x_axis.z, y_axis.z, z_axis.z, location.z),
                (0.0, 0.0, 0.0, 1.0),
            )
        )
    return Matrix.Translation(location)


def _fit_report(obj_a, obj_b, depsgraph, minimum_clearance_mm):
    evaluated_a, mesh_a = _mesh_payload(obj_a, depsgraph)
    evaluated_b, mesh_b = _mesh_payload(obj_b, depsgraph)
    try:
        bbox_a = bbox_from_corners((evaluated_a.matrix_world @ Vector(corner))[:] for corner in evaluated_a.bound_box)
        bbox_b = bbox_from_corners((evaluated_b.matrix_world @ Vector(corner))[:] for corner in evaluated_b.bound_box)
        tree_a = _mesh_bvh(mesh_a)
        tree_b = _mesh_bvh(mesh_b)
        overlaps = tree_a.overlap(tree_b)
        closest_distance = float("inf")
        for vertex in mesh_a.vertices:
            nearest = tree_b.find_nearest(vertex.co)
            if nearest:
                closest_distance = min(closest_distance, (nearest[0] - vertex.co).length)
        for vertex in mesh_b.vertices:
            nearest = tree_a.find_nearest(vertex.co)
            if nearest:
                closest_distance = min(closest_distance, (nearest[0] - vertex.co).length)
        if overlaps:
            overlap_mm = [value * 1000.0 for value in bbox_overlap(bbox_a, bbox_b)]
            penetration_mm = max(min(overlap_mm), 0.0)
            translation_mm = [value * 1000.0 for value in bbox_minimum_translation(bbox_a, bbox_b)]
            return {
                "object_a": obj_a.name,
                "object_b": obj_b.name,
                "status": "interference",
                "interference_mm": penetration_mm,
                "overlap_mm": overlap_mm,
                "suggested_translation_mm": translation_mm,
                "note": f"Interference of {penetration_mm:.3f}mm detected",
            }
        clearance_mm = 0.0 if closest_distance == float("inf") else closest_distance * 1000.0
        if minimum_clearance_mm > 0.0 and clearance_mm > minimum_clearance_mm:
            note = f"Clearance too large ({clearance_mm:.3f}mm)"
        elif minimum_clearance_mm > 0.0 and clearance_mm < minimum_clearance_mm:
            note = f"Clearance too tight ({clearance_mm:.3f}mm)"
        else:
            note = f"Clearance {clearance_mm:.3f}mm"
        return {
            "object_a": obj_a.name,
            "object_b": obj_b.name,
            "status": "clearance",
            "clearance_mm": clearance_mm,
            "minimum_clearance_mm": minimum_clearance_mm,
            "note": note,
        }
    finally:
        evaluated_a.to_mesh_clear()
        evaluated_b.to_mesh_clear()


def inspect_scene():
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return {
        "objects": [
            {
                "name": obj.name,
                "type": obj.type,
                "location": list(obj.location),
                "rotation_euler": list(obj.rotation_euler),
                "scale": list(obj.scale),
                "materials": [slot.material.name for slot in obj.material_slots if slot.material],
                **(
                    {
                        "dimensions": list(obj.evaluated_get(depsgraph).dimensions),
                        "bounding_box": _mesh_world_bbox(obj, depsgraph)["corners"],
                    }
                    if obj.type == "MESH"
                    else {}
                ),
            }
            for obj in scene.objects
        ],
        "materials": [mat.name for mat in bpy.data.materials],
        "camera": scene.camera.name if scene.camera else None,
        "lights": [obj.name for obj in scene.objects if obj.type == "LIGHT"],
    }


def scene_check_overlap(params):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    names = set(params.get("object_names") or [])
    objects = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and (not names or obj.name in names)
    ]
    bounds = {obj.name: _mesh_world_bbox(obj, depsgraph) for obj in objects}
    overlaps = []
    for index, first in enumerate(objects):
        for second in objects[index + 1 :]:
            bbox_a = bounds[first.name]
            bbox_b = bounds[second.name]
            if not bbox_intersects(bbox_a, bbox_b):
                continue
            overlap_mm = [value * 1000.0 for value in bbox_overlap(bbox_a, bbox_b)]
            overlaps.append(
                {
                    "object_a": first.name,
                    "object_b": second.name,
                    "overlap_mm": overlap_mm,
                    "intersection_volume_mm3": overlap_mm[0] * overlap_mm[1] * overlap_mm[2],
                }
            )
    return {"overlaps": overlaps, "checked_objects": [obj.name for obj in objects]}


def mesh_create_gear(params):
    spec = gear_spec(
        module=float(params["module"]),
        teeth_count=int(params["teeth_count"]),
        pressure_angle=float(params.get("pressure_angle", 20.0)),
        width=float(params["width"]),
        backlash=float(params.get("backlash", 0.0)),
    )
    obj = _profile_mesh(params.get("object_name", "Gear"), gear_profile_points(spec), spec.width)
    if params.get("location") is not None:
        obj.location = _vector3(params["location"])
    if params.get("rotation") is not None:
        obj.rotation_euler = _vector3(params["rotation"])
    if params.get("scale") is not None:
        obj.scale = _vector3(params["scale"], (1.0, 1.0, 1.0))
    return spec.as_dict() | {"object_name": obj.name}


def mesh_create_joint(params):
    spec = joint_spec(
        params.get("kind", "male"),
        diameter=float(params["diameter"]),
        length=float(params["length"]),
        clearance=float(params.get("clearance", 0.0)),
        wall_thickness=float(params.get("wall_thickness", 0.0)),
    )
    segments = int(params.get("segments", 32))
    profile = joint_profile_points(spec, segments=segments)
    obj = _profile_mesh(params.get("object_name", "Joint"), profile, spec.length)
    if params.get("location") is not None:
        obj.location = _vector3(params["location"])
    if params.get("rotation") is not None:
        obj.rotation_euler = _vector3(params["rotation"])
    if params.get("scale") is not None:
        obj.scale = _vector3(params["scale"], (1.0, 1.0, 1.0))
    return spec.as_dict() | {"object_name": obj.name, "segments": segments}


def object_define_anchor(params):
    obj = _object(params["object_name"])
    local_location = Vector(_vector3(params.get("location"), (0.0, 0.0, 0.0)))
    world_location = obj.matrix_world @ local_location
    return {
        "object_name": obj.name,
        "anchor_name": params["anchor_name"],
        "location": list(local_location),
        "world_location": [world_location.x, world_location.y, world_location.z],
        "normal": [float(value) for value in params.get("normal")] if params.get("normal") is not None else None,
        "up": [float(value) for value in params.get("up")] if params.get("up") is not None else None,
        "metadata": dict(params.get("metadata") or {}),
    }


def object_mate(params):
    source = _object(params["object_name"])
    target = _object(params["target_object_name"])
    source_anchor = _frame_matrix(params["source_anchor"])
    target_anchor = _frame_matrix(params["target_anchor"])
    source_world = source.matrix_world @ source_anchor
    target_world = target.matrix_world @ target_anchor
    transform = target_world @ source_world.inverted()
    source.matrix_world = transform @ source.matrix_world
    return {
        "object_name": source.name,
        "target_object_name": target.name,
        "anchor_name": params["anchor_name"],
        "target_anchor_name": params["target_anchor_name"],
        "transform_matrix": [list(row) for row in transform],
        "source_world_anchor": [list(row) for row in source_world],
        "target_world_anchor": [list(row) for row in target_world],
    }


def scene_verify_mechanical_fit(params):
    minimum_clearance_mm = float(params.get("minimum_clearance_mm", 0.0))
    names = set(params.get("object_names") or [])
    depsgraph = bpy.context.evaluated_depsgraph_get()
    objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and (not names or obj.name in names)]
    reports = []
    for index, first in enumerate(objects):
        for second in objects[index + 1 :]:
            reports.append(_fit_report(first, second, depsgraph, minimum_clearance_mm))
    return {
        "minimum_clearance_mm": minimum_clearance_mm,
        "checked_objects": [obj.name for obj in objects],
        "pairs": reports,
    }


def scene_import(params):
    path = params["path"]
    suffix = Path(path).suffix.lower()
    if suffix == ".blend":
        with bpy.data.libraries.load(path, link=False) as (source, target):
            target.objects = source.objects
        for obj in target.objects:
            if obj:
                bpy.context.scene.collection.objects.link(obj)
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif suffix == ".stl":
        bpy.ops.wm.stl_import(filepath=path)
    elif suffix in {".gltf", ".glb"}:
        bpy.ops.import_scene.gltf(filepath=path)
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif suffix in {".usd", ".usda", ".usdc", ".usdz"}:
        bpy.ops.wm.usd_import(filepath=path)
    else:
        raise ValueError(f"Unsupported import format: {suffix}")


def object_transform(params):
    obj = _object(params["object_name"])
    if params.get("location") is not None:
        obj.location = _vector(params["location"])
    if params.get("rotation") is not None:
        obj.rotation_euler = _vector(params["rotation"])
    if params.get("scale") is not None:
        obj.scale = _vector(params["scale"], (1.0, 1.0, 1.0))


def material_create_assign(params):
    obj = _object(params["object_name"])
    material = bpy.data.materials.get(params["material_name"]) or bpy.data.materials.new(params["material_name"])
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        raise RuntimeError("Principled BSDF node unavailable")
    color = params.get("base_color", [0.8, 0.8, 0.8, 1.0])
    bsdf.inputs["Base Color"].default_value = tuple(color)
    bsdf.inputs["Roughness"].default_value = params.get("roughness", 0.5)
    bsdf.inputs["Metallic"].default_value = params.get("metallic", 0.0)
    alpha = params.get("alpha", color[3] if len(color) == 4 else 1.0)
    bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1.0:
        material.surface_render_method = "DITHERED"
    texture_path = params.get("texture_path")
    if texture_path:
        texture = material.node_tree.nodes.new("ShaderNodeTexImage")
        texture.image = bpy.data.images.load(texture_path, check_existing=True)
        material.node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
        material.node_tree.links.new(texture.outputs["Alpha"], bsdf.inputs["Alpha"])
    obj.data.materials.clear()
    obj.data.materials.append(material)


def camera_light_setup(params):
    scene = bpy.context.scene
    camera_data = bpy.data.cameras.get(params.get("camera_name", "Camera"))
    if not camera_data:
        camera_data = bpy.data.cameras.new(params.get("camera_name", "Camera"))
    camera = bpy.data.objects.get(camera_data.name) or bpy.data.objects.new(camera_data.name, camera_data)
    if camera.name not in scene.collection.objects:
        scene.collection.objects.link(camera)
    camera.location = _vector(params.get("camera_location"), (4.0, -4.0, 3.0))
    camera.rotation_euler = _vector(params.get("camera_rotation"), (math.radians(65), 0.0, math.radians(45)))
    camera_data.lens = params.get("lens", 50.0)
    scene.camera = camera
    light_name = params.get("light_name", "Key")
    light_data = bpy.data.lights.get(light_name) or bpy.data.lights.new(light_name, params.get("light_type", "AREA"))
    light = bpy.data.objects.get(light_name) or bpy.data.objects.new(light_name, light_data)
    if light.name not in scene.collection.objects:
        scene.collection.objects.link(light)
    light.location = _vector(params.get("light_location"), (4.0, -4.0, 5.0))
    light.rotation_euler = _vector(params.get("light_rotation"))
    light_data.energy = params.get("energy", 1000.0)
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = tuple(
        params.get("world_color", [0.05, 0.05, 0.05, 1.0])
    )


def mesh_create(params):
    name = params.get("object_name", "Mesh")
    primitive = params.get("primitive")
    if primitive:
        operators = {
            "cube": bpy.ops.mesh.primitive_cube_add,
            "uv_sphere": bpy.ops.mesh.primitive_uv_sphere_add,
            "cylinder": bpy.ops.mesh.primitive_cylinder_add,
            "plane": bpy.ops.mesh.primitive_plane_add,
            "cone": bpy.ops.mesh.primitive_cone_add,
        }
        if primitive not in operators:
            raise ValueError(f"Unsupported primitive: {primitive}")
        operators[primitive](location=_vector(params.get("location")), scale=_vector(params.get("scale"), (1, 1, 1)))
        bpy.context.object.name = name
        return
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(params.get("vertices", []), [], params.get("faces", []))
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)


def mesh_modify(params):
    obj = _object(params["object_name"])
    kind = params["modifier"].upper()
    allowed = {"BOOLEAN", "REMESH", "DECIMATE", "SOLIDIFY"}
    if kind not in allowed:
        raise ValueError(f"Unsupported modifier: {kind}")
    mod = obj.modifiers.new(params.get("name", kind.title()), kind)
    options = params.get("parameters", {})
    if kind == "BOOLEAN":
        mod.object = _object(options["operand_object"])
        mod.operation = options.get("operation", "DIFFERENCE")
        mod.solver = options.get("solver", "EXACT")
    elif kind == "DECIMATE":
        mod.ratio = float(options.get("ratio", 0.5))
    elif kind == "SOLIDIFY":
        mod.thickness = float(options.get("thickness", 0.01))
    elif kind == "REMESH":
        if hasattr(mod, "voxel_size") and "voxel_size" in options:
            mod.voxel_size = float(options["voxel_size"])
        if "octree_depth" in options:
            mod.octree_depth = int(options["octree_depth"])
    if params.get("apply", False):
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.modifier_apply(modifier=mod.name)


def mesh_repair(params):
    mesh = _object(params["object_name"]).data
    mesh.validate(clean_customdata=True)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    if params.get("weld", True):
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=float(params.get("weld_distance", 1e-6)))
    if params.get("fill_holes", True):
        bmesh.ops.holes_fill(bm, edges=[edge for edge in bm.edges if edge.is_boundary], sides=0)
    if params.get("recalculate_normals", True):
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if params.get("triangulate", False):
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def scene_export(params):
    output = params["output"]
    suffix = Path(output).suffix.lower()
    if suffix == ".obj":
        bpy.ops.wm.obj_export(filepath=output, export_selected_objects=False, apply_modifiers=True)
    elif suffix == ".stl":
        bpy.ops.wm.stl_export(filepath=output, export_selected_objects=False, apply_modifiers=True)
    elif suffix in {".glb", ".gltf"}:
        bpy.ops.export_scene.gltf(filepath=output, export_format="GLB" if suffix == ".glb" else "GLTF_SEPARATE")
    elif suffix == ".fbx":
        bpy.ops.export_scene.fbx(filepath=output, use_selection=False, use_mesh_modifiers=True)
    elif suffix in {".usd", ".usda", ".usdc"}:
        bpy.ops.wm.usd_export(filepath=output)
    elif suffix == ".3mf" and hasattr(bpy.ops.export_mesh, "threemf"):
        bpy.ops.export_mesh.threemf(filepath=output)
    else:
        raise ValueError(f"Unsupported or unavailable export format: {suffix}")


def render_settings(params):
    scene = bpy.context.scene
    engine = params.get("engine", "BLENDER_EEVEE_NEXT")
    scene.render.engine = "CYCLES" if engine.upper() == "CYCLES" else "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = int(params.get("width", 1024))
    scene.render.resolution_y = int(params.get("height", 1024))
    scene.render.resolution_percentage = 100
    fmt = params.get("format", "PNG").upper()
    scene.render.image_settings.file_format = {"EXR": "OPEN_EXR"}.get(fmt, fmt)
    scene.render.image_settings.color_mode = "RGB" if fmt in {"JPEG", "JPG"} else "RGBA"
    scene.render.film_transparent = bool(params.get("transparent", False))


def render_still(params):
    render_settings(params)
    bpy.context.scene.render.filepath = params["output"]
    bpy.ops.render.render(write_still=True)


def render_turntable(params):
    render_settings(params)
    scene = bpy.context.scene
    camera = scene.camera
    if not camera:
        raise ValueError("A scene camera is required for a turntable render")
    center = _vector(params.get("center"))
    count = int(params.get("frames", 8))
    radius = float(params.get("radius", 5.0))
    output_dir = Path(params["output_dir"])
    for index in range(count):
        theta = 2 * math.pi * index / count
        camera.location = (center[0] + radius * math.cos(theta), center[1] + radius * math.sin(theta), camera.location.z)
        direction = (Vector(center) - camera.location).to_track_quat("-Z", "Y")
        camera.rotation_euler = direction.to_euler()
        scene.render.filepath = str(output_dir / f"view_{index:03d}.png")
        bpy.ops.render.render(write_still=True)


def render_object_mask(params):
    scene = bpy.context.scene
    render_settings({**params, "format": "PNG"})
    layer = bpy.context.view_layer
    material_mode = params.get("selector_type", "object") == "material"
    layer.use_pass_cryptomatte_material = material_mode
    layer.use_pass_cryptomatte_object = not material_mode
    layer.pass_cryptomatte_depth = 6
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    render_layers = tree.nodes.new("CompositorNodeRLayers")
    crypto = tree.nodes.new("CompositorNodeCryptomatteV2")
    crypto.source = "RENDER"
    crypto.layer_name = f"{layer.name}.{'CryptoMaterial' if material_mode else 'CryptoObject'}"
    crypto.matte_id = params["selector_name"]
    output = tree.nodes.new("CompositorNodeOutputFile")
    output.base_path = str(Path(params["output"]).parent)
    output.format.file_format = "PNG"
    output.file_slots[0].path = Path(params["output"]).stem + "_"
    tree.links.new(render_layers.outputs["Image"], crypto.inputs["Image"])
    tree.links.new(crypto.outputs["Matte"], output.inputs[0])
    scene.render.filepath = str(Path(params["output"]).with_name("_mask_beauty.png"))
    bpy.ops.render.render(write_still=True)
    generated = sorted(Path(output.base_path).glob(Path(params["output"]).stem + "_*.png"))
    if not generated:
        raise RuntimeError("Cryptomatte output was not written")
    generated[-1].replace(params["output"])


def compositor_apply(params):
    scene = bpy.context.scene
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    image_node = tree.nodes.new("CompositorNodeImage")
    image_node.image = bpy.data.images.load(params["input"], check_existing=False)
    current = image_node.outputs["Image"]
    action = params["effect"]
    if action == "blur":
        node = tree.nodes.new("CompositorNodeBlur")
        node.size_x = node.size_y = int(params.get("size", 8))
        tree.links.new(current, node.inputs[0])
    elif action == "transform":
        node = tree.nodes.new("CompositorNodeTransform")
        node.inputs["X"].default_value = float(params.get("x", 0))
        node.inputs["Y"].default_value = float(params.get("y", 0))
        tree.links.new(current, node.inputs[0])
    elif action == "alpha_over":
        node = tree.nodes.new("CompositorNodeAlphaOver")
        overlay = tree.nodes.new("CompositorNodeImage")
        overlay.image = bpy.data.images.load(params["overlay"], check_existing=False)
        tree.links.new(current, node.inputs[1])
        tree.links.new(overlay.outputs["Image"], node.inputs[2])
    elif action == "mask_composite":
        node = tree.nodes.new("CompositorNodeAlphaOver")
        overlay = tree.nodes.new("CompositorNodeImage")
        overlay.image = bpy.data.images.load(params["overlay"], check_existing=False)
        mask = tree.nodes.new("CompositorNodeImage")
        mask.image = bpy.data.images.load(params["mask"], check_existing=False)
        set_alpha = tree.nodes.new("CompositorNodeSetAlpha")
        tree.links.new(overlay.outputs["Image"], set_alpha.inputs["Image"])
        tree.links.new(mask.outputs["Image"], set_alpha.inputs["Alpha"])
        tree.links.new(current, node.inputs[1])
        tree.links.new(set_alpha.outputs["Image"], node.inputs[2])
    else:
        raise ValueError(f"Unsupported compositor effect: {action}")
    composite = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(node.outputs[0], composite.inputs[0])
    scene.render.filepath = params["output"]
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)


def unsafe_python(params):
    exec(compile(params["code"], "<blender_run_python>", "exec"), {"bpy": bpy, "bmesh": bmesh})


HANDLERS = {
    "init": lambda _: None,
    "scene_import": scene_import,
    "object_transform": object_transform,
    "object_delete": lambda params: bpy.data.objects.remove(_object(params["object_name"]), do_unlink=True),
    "material_create_assign": material_create_assign,
    "camera_light_setup": camera_light_setup,
    "mesh_create": mesh_create,
    "mesh_create_gear": mesh_create_gear,
    "mesh_create_joint": mesh_create_joint,
    "mesh_modify": mesh_modify,
    "mesh_repair": mesh_repair,
    "scene_export": scene_export,
    "render_still": render_still,
    "render_turntable": render_turntable,
    "render_object_mask": render_object_mask,
    "compositor_apply": compositor_apply,
    "scene_check_overlap": scene_check_overlap,
    "scene_verify_mechanical_fit": scene_verify_mechanical_fit,
    "object_define_anchor": object_define_anchor,
    "object_mate": object_mate,
    "unsafe_python": unsafe_python,
}
