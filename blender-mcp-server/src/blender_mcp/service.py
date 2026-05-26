from __future__ import annotations

from pathlib import Path
from typing import Any

from .blender import BlenderExecutor
from .config import PathPolicy, PathValidationError, Settings
from .jobs import JobStore
from .segmentation import ImageEditor, Segmenter


IMPORT_SUFFIXES = {".blend", ".obj", ".stl", ".gltf", ".glb", ".fbx", ".usd", ".usda", ".usdc", ".usdz"}
EXPORT_SUFFIXES = {".obj", ".stl", ".gltf", ".glb", ".fbx", ".usd", ".usda", ".usdc", ".3mf"}


class BlenderMCPService:
    def __init__(
        self,
        settings: Settings,
        *,
        executor: BlenderExecutor | None = None,
        segmenter: Segmenter | None = None,
    ):
        self.settings = settings
        self.paths = PathPolicy(settings)
        self.store = JobStore(self.paths)
        self.executor = executor or BlenderExecutor(settings, self.store)
        self.segmenter = segmenter or Segmenter(settings, self.paths, self.store)
        self.editor = ImageEditor(self.paths, self.store)

    def blender_healthcheck(self) -> dict[str, Any]:
        return self.executor.healthcheck()

    def job_create(self, source_blend: str | None = None) -> dict[str, Any]:
        manifest = self.store.create()
        if source_blend:
            source = self.paths.input_file(source_blend, {".blend"})
            self.executor.run(manifest["job_id"], "init", {}, mutate_scene=True, source_scene=source)
        else:
            self.executor.run(manifest["job_id"], "init", {}, mutate_scene=True)
        return self.store.load(manifest["job_id"])

    def job_inspect(self, job_id: str) -> dict[str, Any]:
        manifest = self.store.load(job_id)
        if self.store.current_scene(job_id):
            manifest["scene"] = self.executor.run(job_id, "inspect", {}, mutate_scene=False)
        return manifest

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
        output_dir.mkdir(exist_ok=True)
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

    def blender_run_python(self, job_id: str, code: str, timeout: float | None = None):
        if not self.settings.unsafe_python:
            raise PermissionError("Set BLENDER_MCP_ENABLE_UNSAFE_PYTHON=1 to enable arbitrary Blender Python.")
        return self.executor.run(job_id, "unsafe_python", {"code": code}, timeout=timeout)

    @staticmethod
    def _validate_filename(filename: str, suffixes: set[str], artifact_type: str) -> None:
        if Path(filename).name != filename or Path(filename).suffix.lower() not in suffixes:
            raise ValueError(f"{artifact_type.title()} filename must be a supported plain filename")

    def _image_source(self, value: str) -> Path:
        try:
            return self.paths.existing_output_file(value)
        except PathValidationError:
            return self.paths.input_file(value, {".png", ".jpg", ".jpeg", ".webp"})
