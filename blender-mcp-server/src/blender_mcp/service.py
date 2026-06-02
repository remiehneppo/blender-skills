from __future__ import annotations

from typing import Any

from .blender import BlenderExecutor
from .config import PathPolicy, Settings
from .jobs import JobStore
from .service_facades import ImageFacade, MechanicalFacade, RenderFacade, SceneFacade, ServiceContext
from .segmentation import ImageEditor, Segmenter


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
        self._segmenter = segmenter or Segmenter(settings, self.paths, self.store)
        self.editor = ImageEditor(self.paths, self.store)
        self.context = ServiceContext(
            settings=self.settings,
            paths=self.paths,
            store=self.store,
            executor=self.executor,
            segmenter=self._segmenter,
            editor=self.editor,
        )
        self.scene = SceneFacade(self.context)
        self.render = RenderFacade(self.context)
        self.image = ImageFacade(self.context)
        self.mechanical = MechanicalFacade(self.context)

    @property
    def segmenter(self) -> Segmenter:
        return self._segmenter

    @segmenter.setter
    def segmenter(self, value: Segmenter) -> None:
        self._segmenter = value
        self.context.segmenter = value

    def blender_healthcheck(self) -> dict[str, Any]:
        return self.executor.healthcheck()

    def job_create(self, source_blend: str | None = None) -> dict[str, Any]:
        return self.scene.job_create(source_blend)

    def job_inspect(self, job_id: str) -> dict[str, Any]:
        return self.scene.job_inspect(job_id)

    def scene_check_overlap(self, job_id: str, object_names: list[str] | None = None) -> dict[str, Any]:
        return self.scene.scene_check_overlap(job_id, object_names)

    def scene_import(self, job_id: str, path: str) -> dict[str, Any]:
        return self.scene.scene_import(job_id, path)

    def object_transform(self, job_id: str, object_name: str, **transform: Any) -> dict[str, Any]:
        return self.scene.object_transform(job_id, object_name, **transform)

    def object_delete(self, job_id: str, object_name: str) -> dict[str, Any]:
        return self.scene.object_delete(job_id, object_name)

    def material_create_assign(self, job_id: str, object_name: str, material_name: str, **material: Any) -> dict[str, Any]:
        return self.scene.material_create_assign(job_id, object_name, material_name, **material)

    def camera_light_setup(self, job_id: str, **params: Any) -> dict[str, Any]:
        return self.scene.camera_light_setup(job_id, **params)

    def mesh_create(self, job_id: str, **params: Any) -> dict[str, Any]:
        return self.scene.mesh_create(job_id, **params)

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
        return self.mechanical.mesh_create_gear(
            job_id,
            object_name,
            module,
            teeth_count,
            width,
            pressure_angle=pressure_angle,
            backlash=backlash,
            **params,
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
        return self.mechanical.mesh_create_joint(
            job_id,
            object_name,
            kind,
            diameter,
            length,
            clearance=clearance,
            wall_thickness=wall_thickness,
            segments=segments,
            **params,
        )

    def mesh_modify(self, job_id: str, object_name: str, modifier: str, **params: Any) -> dict[str, Any]:
        return self.scene.mesh_modify(job_id, object_name, modifier, **params)

    def mesh_repair(self, job_id: str, object_name: str, **params: Any) -> dict[str, Any]:
        return self.scene.mesh_repair(job_id, object_name, **params)

    def scene_export(self, job_id: str, filename: str) -> dict[str, str]:
        return self.render.scene_export(job_id, filename)

    def render_still(self, job_id: str, filename: str = "render.png", **params: Any) -> dict[str, str]:
        return self.render.render_still(job_id, filename, **params)

    def render_turntable(self, job_id: str, **params: Any) -> dict[str, str]:
        return self.render.render_turntable(job_id, **params)

    def render_object_mask(
        self, job_id: str, selector_name: str, selector_type: str = "object", filename: str = "mask.png", **params: Any
    ) -> dict[str, str]:
        return self.render.render_object_mask(job_id, selector_name, selector_type, filename, **params)

    def compositor_apply(self, job_id: str, input_path: str, effect: str, filename: str = "composite.png", **params: Any):
        return self.render.compositor_apply(job_id, input_path, effect, filename, **params)

    def image_segment(self, job_id: str, input_path: str, **params: Any) -> dict[str, Any]:
        return self.image.image_segment(job_id, input_path, **params)

    def image_edit_by_mask(self, job_id: str, input_path: str, instance_id: str, action: str, **params: Any):
        return self.image.image_edit_by_mask(job_id, input_path, instance_id, action, **params)

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
        return self.mechanical.object_define_anchor(
            job_id,
            object_name,
            anchor_name,
            location=location,
            normal=normal,
            up=up,
            **metadata,
        )

    def object_mate(
        self,
        job_id: str,
        object_name: str,
        anchor_name: str,
        target_object_name: str,
        target_anchor_name: str,
    ) -> dict[str, Any]:
        return self.mechanical.object_mate(job_id, object_name, anchor_name, target_object_name, target_anchor_name)

    def scene_verify_mechanical_fit(
        self,
        job_id: str,
        object_names: list[str] | None = None,
        *,
        minimum_clearance_mm: float = 0.0,
    ) -> dict[str, Any]:
        return self.mechanical.scene_verify_mechanical_fit(
            job_id, object_names=object_names, minimum_clearance_mm=minimum_clearance_mm
        )

    def blender_run_python(self, job_id: str, code: str, timeout: float | None = None):
        if not self.settings.unsafe_python:
            raise PermissionError("Set BLENDER_MCP_ENABLE_UNSAFE_PYTHON=1 to enable arbitrary Blender Python.")
        return self.executor.run(job_id, "unsafe_python", {"code": code}, timeout=timeout)
