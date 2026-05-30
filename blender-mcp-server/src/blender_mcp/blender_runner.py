"""Executed by Blender, not imported by the MCP process."""

from __future__ import annotations

import json
import math
import sys
import traceback
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


def _vector(value, default=(0.0, 0.0, 0.0)):
    return tuple(value if value is not None else default)


def _load(payload):
    source = payload.get("source_scene")
    if source:
        bpy.ops.wm.open_mainfile(filepath=source)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)


def _disable_backup_versions():
    try:
        bpy.context.preferences.filepaths.save_version = 0
    except Exception:
        pass


def _object(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"Object not found: {name}")
    return obj


def _inspect():
    scene = bpy.context.scene
    return {
        "objects": [
            {
                "name": obj.name,
                "type": obj.type,
                "location": list(obj.location),
                "rotation_euler": list(obj.rotation_euler),
                "scale": list(obj.scale),
                "materials": [slot.material.name for slot in obj.material_slots if slot.material],
            }
            for obj in scene.objects
        ],
        "materials": [mat.name for mat in bpy.data.materials],
        "camera": scene.camera.name if scene.camera else None,
        "lights": [obj.name for obj in scene.objects if obj.type == "LIGHT"],
    }


def _scene_import(params):
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


def _object_transform(params):
    obj = _object(params["object_name"])
    if params.get("location") is not None:
        obj.location = _vector(params["location"])
    if params.get("rotation") is not None:
        obj.rotation_euler = _vector(params["rotation"])
    if params.get("scale") is not None:
        obj.scale = _vector(params["scale"], (1.0, 1.0, 1.0))


def _material_create_assign(params):
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


def _camera_light_setup(params):
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


def _mesh_create(params):
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


def _mesh_modify(params):
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


def _mesh_repair(params):
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


def _scene_export(params):
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


def _render_settings(params):
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


def _render_still(params):
    _render_settings(params)
    bpy.context.scene.render.filepath = params["output"]
    bpy.ops.render.render(write_still=True)


def _render_turntable(params):
    _render_settings(params)
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


def _render_object_mask(params):
    scene = bpy.context.scene
    _render_settings({**params, "format": "PNG"})
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


def _compositor_apply(params):
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


def _unsafe_python(params):
    exec(compile(params["code"], "<blender_run_python>", "exec"), {"bpy": bpy, "bmesh": bmesh})


HANDLERS = {
    "init": lambda _: None,
    "scene_import": _scene_import,
    "object_transform": _object_transform,
    "object_delete": lambda params: bpy.data.objects.remove(_object(params["object_name"]), do_unlink=True),
    "material_create_assign": _material_create_assign,
    "camera_light_setup": _camera_light_setup,
    "mesh_create": _mesh_create,
    "mesh_modify": _mesh_modify,
    "mesh_repair": _mesh_repair,
    "scene_export": _scene_export,
    "render_still": _render_still,
    "render_turntable": _render_turntable,
    "render_object_mask": _render_object_mask,
    "compositor_apply": _compositor_apply,
    "unsafe_python": _unsafe_python,
}


def main():
    payload_path, response_path = [Path(value) for value in sys.argv[sys.argv.index("--") + 1 :]]
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        _disable_backup_versions()
        _load(payload)
        _disable_backup_versions()
        action = payload["action"]
        if action == "inspect":
            result = _inspect()
        else:
            HANDLERS[action](payload.get("params", {}))
            result = _inspect()
            if payload.get("output_scene"):
                bpy.ops.wm.save_as_mainfile(filepath=payload["output_scene"])
        response_path.write_text(json.dumps({"ok": True, "result": result}), encoding="utf-8")
    except Exception as exc:
        response_path.write_text(
            json.dumps({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}), encoding="utf-8"
        )
        raise


if __name__ == "__main__":
    main()
