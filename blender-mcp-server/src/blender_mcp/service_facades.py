from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .blender import BlenderExecutor
from .config import PathPolicy, PathValidationError, Settings
from .jobs import JobStore
from .gear import gear_spec
from .joints import joint_spec
from .segmentation import ImageEditor, Segmenter


IMPORT_SUFFIXES = {".blend", ".obj", ".stl", ".gltf", ".glb", ".fbx", ".usd", ".usda", ".usdc", ".usdz"}
EXPORT_SUFFIXES = {".obj", ".stl", ".gltf", ".glb", ".fbx", ".usd", ".usda", ".usdc", ".3mf"}


@dataclass(slots=True)
class ServiceContext:
    settings: Settings
    paths: PathPolicy
    store: JobStore
    executor: BlenderExecutor
    segmenter: Segmenter
    editor: ImageEditor


class _FacadeBase:
    def __init__(self, context: ServiceContext):
        self.context = context

    @property
    def settings(self) -> Settings:
        return self.context.settings

    @property
    def paths(self) -> PathPolicy:
        return self.context.paths

    @property
    def store(self) -> JobStore:
        return self.context.store

    @property
    def executor(self) -> BlenderExecutor:
        return self.context.executor

    @property
    def segmenter(self) -> Segmenter:
        return self.context.segmenter

    @property
    def editor(self) -> ImageEditor:
        return self.context.editor

    @staticmethod
    def _validate_filename(filename: str, suffixes: set[str], artifact_type: str) -> None:
        if Path(filename).name != filename or Path(filename).suffix.lower() not in suffixes:
            raise ValueError(f"{artifact_type.title()} filename must be a supported plain filename")

    def _image_source(self, value: str) -> Path:
        try:
            return self.paths.existing_output_file(value)
        except PathValidationError:
            return self.paths.input_file(value, {".png", ".jpg", ".jpeg", ".webp"})


class SceneFacade(_FacadeBase):
    def job_create(self, source_blend: str | None = None) -> dict[str, Any]:
        source = self.paths.input_file(source_blend, {".blend"}) if source_blend else None
        manifest = self.store.create()
        if source:
            self.executor.run(manifest["job_id"], "init", {}, mutate_scene=True, source_scene=source)
        else:
            self.executor.run(manifest["job_id"], "init", {}, mutate_scene=True)
        return self.store.load(manifest["job_id"])

    def job_inspect(self, job_id: str) -> dict[str, Any]:
        manifest = self.store.load(job_id)
        if self.store.current_scene(job_id):
            manifest["scene"] = self.executor.run(job_id, "inspect", {}, mutate_scene=False)
        return manifest

    def scene_check_overlap(self, job_id: str, object_names: list[str] | None = None) -> dict[str, Any]:
        return self.executor.run(
            job_id, "scene_check_overlap", {"object_names": object_names or []}, mutate_scene=False
        )

    def scene_import(self, job_id: str, path: str) -> dict[str, Any]:
        source = self.paths.input_file(path, IMPORT_SUFFIXES)
        return self.executor.run(job_id, "scene_import", {"path": str(source)})

    def object_transform(self, job_id: str, object_name: str, **transform: Any) -> dict[str, Any]:
        return self.executor.run(job_id, "object_transform", {"object_name": object_name, **transform})

    def object_delete(self, job_id: str, object_name: str) -> dict[str, Any]:
        return self.executor.run(job_id, "object_delete", {"object_name": object_name})

    def material_create_assign(self, job_id: str, object_name: str, material_name: str, **material: Any) -> dict[str, Any]:
        if material.get("texture_path"):
            material["texture_path"] = str(self.paths.input_file(material["texture_path"]))
        return self.executor.run(
            job_id, "material_create_assign", {"object_name": object_name, "material_name": material_name, **material}
        )

    def camera_light_setup(self, job_id: str, **params: Any) -> dict[str, Any]:
        return self.executor.run(job_id, "camera_light_setup", params)

    def mesh_create(self, job_id: str, **params: Any) -> dict[str, Any]:
        return self.executor.run(job_id, "mesh_create", params)

    def mesh_modify(self, job_id: str, object_name: str, modifier: str, **params: Any) -> dict[str, Any]:
        return self.executor.run(job_id, "mesh_modify", {"object_name": object_name, "modifier": modifier, **params})

    def mesh_repair(self, job_id: str, object_name: str, **params: Any) -> dict[str, Any]:
        return self.executor.run(job_id, "mesh_repair", {"object_name": object_name, **params})


class RenderFacade(_FacadeBase):
    def scene_export(self, job_id: str, filename: str) -> dict[str, str]:
        self._validate_filename(filename, EXPORT_SUFFIXES, "export")
        output = self.store.artifact_path(job_id, filename)
        self.executor.run(job_id, "scene_export", {"output": str(output)}, mutate_scene=False)
        self.store.add_artifact(job_id, "scene_export", output)
        return {"output_path": str(output)}

    def render_still(self, job_id: str, filename: str = "render.png", **params: Any) -> dict[str, str]:
        self._validate_filename(filename, {".png", ".jpg", ".jpeg", ".exr"}, "render")
        expected_format = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".exr": "EXR"}[
            Path(filename).suffix.lower()
        ]
        requested_format = params.pop("format", None)
        if requested_format and requested_format.upper() != expected_format:
            raise ValueError(f"Render format {requested_format} does not match filename {filename}")
        params["format"] = expected_format
        output = self.store.artifact_path(job_id, filename)
        self.executor.run(job_id, "render_still", {"output": str(output), **params}, mutate_scene=False)
        self.store.add_artifact(job_id, "render", output)
        return {"output_path": str(output)}

    def render_turntable(self, job_id: str, **params: Any) -> dict[str, str]:
        output_dir = self.store.directory(job_id) / "artifacts" / "turntable"
        output_dir.mkdir(parents=True, exist_ok=True)
        self.executor.run(job_id, "render_turntable", {"output_dir": str(output_dir), **params}, mutate_scene=False)
        self.store.add_artifact(job_id, "turntable", output_dir)
        return {"output_dir": str(output_dir)}

    def render_object_mask(
        self, job_id: str, selector_name: str, selector_type: str = "object", filename: str = "mask.png", **params: Any
    ) -> dict[str, str]:
        if selector_type not in {"object", "material"}:
            raise ValueError("selector_type must be object or material")
        self._validate_filename(filename, {".png"}, "mask")
        output = self.store.artifact_path(job_id, filename)
        self.executor.run(
            job_id,
            "render_object_mask",
            {"output": str(output), "selector_name": selector_name, "selector_type": selector_type, **params},
            mutate_scene=False,
        )
        self.store.add_artifact(job_id, "cryptomatte_mask", output, {"selector_name": selector_name})
        return {"output_path": str(output)}

    def compositor_apply(self, job_id: str, input_path: str, effect: str, filename: str = "composite.png", **params: Any):
        self._validate_filename(filename, {".png"}, "composite")
        source = self.paths.existing_output_file(input_path)
        if effect not in {"blur", "transform", "alpha_over", "mask_composite"}:
            raise ValueError(f"Unsupported compositor effect: {effect}")
        if effect in {"alpha_over", "mask_composite"}:
            if not params.get("overlay_path"):
                raise ValueError(f"overlay_path is required for {effect}")
            params["overlay"] = str(self._image_source(params.pop("overlay_path")))
        if effect == "mask_composite":
            if not params.get("mask_path"):
                raise ValueError("mask_path is required for mask_composite")
            params["mask"] = str(self.paths.existing_output_file(params.pop("mask_path")))
        output = self.store.artifact_path(job_id, filename)
        self.executor.run(
            job_id, "compositor_apply", {"input": str(source), "effect": effect, "output": str(output), **params}, mutate_scene=False
        )
        self.store.add_artifact(job_id, "composite", output)
        return {"output_path": str(output)}


class ImageFacade(_FacadeBase):
    def image_segment(self, job_id: str, input_path: str, **params: Any) -> dict[str, Any]:
        return self.segmenter.segment(job_id, input_path, **params)

    def image_edit_by_mask(self, job_id: str, input_path: str, instance_id: str, action: str, **params: Any):
        artifact = next(
            (
                item
                for item in self.store.load(job_id)["artifacts"]
                if item["kind"] == "instance_mask" and item["metadata"].get("instance_id") == instance_id
            ),
            None,
        )
        if artifact is None:
            raise ValueError(f"Unknown segmentation instance: {instance_id}")
        mask_path = self.store.directory(job_id) / artifact["path"]
        return self.editor.apply(job_id, input_path, str(mask_path), action, **params)


class MechanicalFacade(_FacadeBase):
    def mesh_create_gear(
        self,
        job_id: str,
        object_name: str,
        module: float,
        teeth_count: int,
        width: float,
        *,
        pressure_angle: float = 20.0,
        backlash: float = 0.0,
        **params: Any,
    ) -> dict[str, Any]:
        spec = gear_spec(module, teeth_count, pressure_angle, width, backlash)
        return self.executor.run(
            job_id,
            "mesh_create_gear",
            {
                "object_name": object_name,
                "module": spec.module,
                "teeth_count": spec.teeth_count,
                "pressure_angle": spec.pressure_angle_deg,
                "width": spec.width,
                "backlash": spec.backlash,
                **params,
            },
        )

    def mesh_create_joint(
        self,
        job_id: str,
        object_name: str,
        kind: str,
        diameter: float,
        length: float,
        *,
        clearance: float = 0.0,
        wall_thickness: float = 0.0,
        segments: int = 32,
        **params: Any,
    ) -> dict[str, Any]:
        spec = joint_spec(kind, diameter, length, clearance=clearance, wall_thickness=wall_thickness)
        return self.executor.run(
            job_id,
            "mesh_create_joint",
            {
                "object_name": object_name,
                "kind": spec.kind,
                "diameter": spec.diameter,
                "length": spec.length,
                "clearance": spec.clearance,
                "wall_thickness": spec.wall_thickness,
                "segments": segments,
                **params,
            },
        )

    def object_define_anchor(
        self,
        job_id: str,
        object_name: str,
        anchor_name: str,
        *,
        location: list[float] | None = None,
        normal: list[float] | None = None,
        up: list[float] | None = None,
        **metadata: Any,
    ) -> dict[str, Any]:
        result = self.executor.run(
            job_id,
            "object_define_anchor",
            {
                "object_name": object_name,
                "anchor_name": anchor_name,
                "location": location,
                "normal": normal,
                "up": up,
                "metadata": metadata,
            },
            mutate_scene=False,
        )
        anchor = self.store.add_anchor(
            job_id,
            object_name,
            anchor_name,
            result["location"],
            normal=result.get("normal"),
            up=result.get("up"),
            metadata=result.get("metadata"),
        )
        return {"anchor": anchor, "scene": result.get("scene")}

    def object_mate(
        self,
        job_id: str,
        object_name: str,
        anchor_name: str,
        target_object_name: str,
        target_anchor_name: str,
    ) -> dict[str, Any]:
        source_anchor = self.store.find_anchor(job_id, object_name, anchor_name)
        if source_anchor is None:
            raise ValueError(f"Unknown anchor: {object_name}.{anchor_name}")
        target_anchor = self.store.find_anchor(job_id, target_object_name, target_anchor_name)
        if target_anchor is None:
            raise ValueError(f"Unknown anchor: {target_object_name}.{target_anchor_name}")
        result = self.executor.run(
            job_id,
            "object_mate",
            {
                "object_name": object_name,
                "anchor_name": anchor_name,
                "target_object_name": target_object_name,
                "target_anchor_name": target_anchor_name,
                "source_anchor": source_anchor,
                "target_anchor": target_anchor,
            },
        )
        mate = self.store.add_mate(
            job_id,
            object_name,
            anchor_name,
            target_object_name,
            target_anchor_name,
            metadata={"transform_matrix": result.get("transform_matrix")},
        )
        return {"mate": mate, "scene": result.get("scene")}

    def scene_verify_mechanical_fit(
        self,
        job_id: str,
        object_names: list[str] | None = None,
        *,
        minimum_clearance_mm: float = 0.0,
    ) -> dict[str, Any]:
        return self.executor.run(
            job_id,
            "scene_verify_mechanical_fit",
            {"object_names": object_names or [], "minimum_clearance_mm": minimum_clearance_mm},
            mutate_scene=False,
        )
