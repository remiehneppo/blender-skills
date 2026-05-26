from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import Settings
from .service import BlenderMCPService


CAPABILITIES = {
    "baseline": "Blender 4.5 LTS+",
    "transport": "stdio",
    "scene_identity_masks": "Cryptomatte Object/Material",
    "external_image_masks": "YOLO11-seg instance masks",
    "segmentation_boundary": (
        "Masks inferred from arbitrary external images are not mapped to 3D scene objects "
        "without corresponding camera/scene data."
    ),
    "tools": [
        "blender_healthcheck",
        "job_create",
        "job_inspect",
        "scene_import",
        "object_transform",
        "object_delete",
        "material_create_assign",
        "camera_light_setup",
        "mesh_create",
        "mesh_modify",
        "mesh_repair",
        "scene_export",
        "render_still",
        "render_turntable",
        "render_object_mask",
        "compositor_apply",
        "image_segment",
        "image_edit_by_mask",
    ],
}


def create_server(settings: Settings | None = None, service: BlenderMCPService | None = None) -> FastMCP:
    settings = settings or Settings.from_env()
    service = service or BlenderMCPService(settings)
    mcp = FastMCP("blender-mcp-server")
    repo_root = Path(__file__).resolve().parents[3]

    @mcp.tool()
    def blender_healthcheck() -> dict[str, Any]:
        """Check Blender 4.5+, writable output storage and configured segmentation weights."""
        return service.blender_healthcheck()

    @mcp.tool()
    def job_create(source_blend: str | None = None) -> dict[str, Any]:
        """Create a versioned Blender job from an empty scene or a workspace .blend file."""
        return service.job_create(source_blend)

    @mcp.tool()
    def job_inspect(job_id: str) -> dict[str, Any]:
        """Inspect job manifest plus Blender objects, materials, camera and lights."""
        return service.job_inspect(job_id)

    @mcp.tool()
    def scene_import(job_id: str, path: str) -> dict[str, Any]:
        """Import a workspace BLEND, OBJ, STL, glTF/GLB, FBX or USD asset into a scene."""
        return service.scene_import(job_id, path)

    @mcp.tool()
    def object_transform(
        job_id: str,
        object_name: str,
        location: list[float] | None = None,
        rotation: list[float] | None = None,
        scale: list[float] | None = None,
    ) -> dict[str, Any]:
        """Set an object's transform using Blender-unit location and radians rotation."""
        return service.object_transform(job_id, object_name, location=location, rotation=rotation, scale=scale)

    @mcp.tool()
    def object_delete(job_id: str, object_name: str) -> dict[str, Any]:
        """Delete a named object from the job scene."""
        return service.object_delete(job_id, object_name)

    @mcp.tool()
    def material_create_assign(
        job_id: str,
        object_name: str,
        material_name: str,
        base_color: list[float] | None = None,
        roughness: float = 0.5,
        metallic: float = 0.0,
        alpha: float = 1.0,
        texture_path: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a Principled material and assign it to a named object."""
        return service.material_create_assign(
            job_id,
            object_name,
            material_name,
            base_color=base_color or [0.8, 0.8, 0.8, alpha],
            roughness=roughness,
            metallic=metallic,
            alpha=alpha,
            texture_path=texture_path,
        )

    @mcp.tool()
    def camera_light_setup(
        job_id: str,
        camera_name: str = "Camera",
        camera_location: list[float] | None = None,
        camera_rotation: list[float] | None = None,
        lens: float = 50.0,
        light_name: str = "Key",
        light_type: str = "AREA",
        light_location: list[float] | None = None,
        light_rotation: list[float] | None = None,
        energy: float = 1000.0,
        world_color: list[float] | None = None,
    ) -> dict[str, Any]:
        """Create or update the active camera, one light and the world background."""
        return service.camera_light_setup(
            job_id,
            camera_name=camera_name,
            camera_location=camera_location,
            camera_rotation=camera_rotation,
            lens=lens,
            light_name=light_name,
            light_type=light_type,
            light_location=light_location,
            light_rotation=light_rotation,
            energy=energy,
            world_color=world_color or [0.05, 0.05, 0.05, 1.0],
        )

    @mcp.tool()
    def mesh_create(
        job_id: str,
        object_name: str = "Mesh",
        primitive: str | None = None,
        vertices: list[list[float]] | None = None,
        faces: list[list[int]] | None = None,
        location: list[float] | None = None,
        scale: list[float] | None = None,
    ) -> dict[str, Any]:
        """Create a supported primitive or construct mesh geometry from vertices and faces."""
        return service.mesh_create(
            job_id,
            object_name=object_name,
            primitive=primitive,
            vertices=vertices or [],
            faces=faces or [],
            location=location,
            scale=scale,
        )

    @mcp.tool()
    def mesh_modify(
        job_id: str, object_name: str, modifier: str, parameters: dict[str, Any] | None = None, apply: bool = False
    ) -> dict[str, Any]:
        """Add Boolean, Remesh, Decimate or Solidify and optionally apply it."""
        return service.mesh_modify(
            job_id, object_name, modifier, parameters=parameters or {}, apply=apply
        )

    @mcp.tool()
    def mesh_repair(
        job_id: str,
        object_name: str,
        weld: bool = True,
        fill_holes: bool = True,
        recalculate_normals: bool = True,
        triangulate: bool = False,
        weld_distance: float = 0.000001,
    ) -> dict[str, Any]:
        """Validate, weld, fill holes, recalculate normals and optionally triangulate a mesh."""
        return service.mesh_repair(
            job_id,
            object_name,
            weld=weld,
            fill_holes=fill_holes,
            recalculate_normals=recalculate_normals,
            triangulate=triangulate,
            weld_distance=weld_distance,
        )

    @mcp.tool()
    def scene_export(job_id: str, filename: str) -> dict[str, str]:
        """Export an artifact as OBJ, STL, glTF/GLB, FBX, USD or available 3MF."""
        return service.scene_export(job_id, filename)

    @mcp.tool()
    def render_still(
        job_id: str,
        filename: str = "render.png",
        engine: str = "BLENDER_EEVEE_NEXT",
        width: int = 1024,
        height: int = 1024,
        format: str | None = None,
        transparent: bool = False,
    ) -> dict[str, str]:
        """Render to PNG, JPEG or EXR; filename extension controls image encoding."""
        return service.render_still(
            job_id, filename, engine=engine, width=width, height=height, format=format, transparent=transparent
        )

    @mcp.tool()
    def render_turntable(
        job_id: str,
        frames: int = 8,
        radius: float = 5.0,
        center: list[float] | None = None,
        engine: str = "BLENDER_EEVEE_NEXT",
        width: int = 1024,
        height: int = 1024,
    ) -> dict[str, str]:
        """Render multiple camera-orbit PNG views into a turntable artifact directory."""
        return service.render_turntable(
            job_id, frames=frames, radius=radius, center=center or [0.0, 0.0, 0.0], engine=engine, width=width, height=height
        )

    @mcp.tool()
    def render_object_mask(
        job_id: str,
        selector_name: str,
        selector_type: str = "object",
        filename: str = "mask.png",
        width: int = 1024,
        height: int = 1024,
    ) -> dict[str, str]:
        """Render an exact Cryptomatte object or material selection mask from a known scene."""
        return service.render_object_mask(
            job_id, selector_name, selector_type, filename, width=width, height=height
        )

    @mcp.tool()
    def compositor_apply(
        job_id: str,
        input_path: str,
        effect: str,
        filename: str = "composite.png",
        size: int = 8,
        x: float = 0.0,
        y: float = 0.0,
        overlay_path: str | None = None,
        mask_path: str | None = None,
    ) -> dict[str, str]:
        """Apply blur, transform, alpha_over or mask_composite to a render artifact."""
        return service.compositor_apply(
            job_id,
            input_path,
            effect,
            filename,
            size=size,
            x=x,
            y=y,
            overlay_path=overlay_path,
            mask_path=mask_path,
        )

    @mcp.tool()
    def image_segment(
        job_id: str,
        input_path: str,
        class_name: str | None = None,
        confidence: float = 0.25,
        device: str | None = None,
    ) -> dict[str, Any]:
        """Use configured YOLO11-seg weights to produce one PNG mask per external-image instance."""
        return service.image_segment(
            job_id, input_path, class_name=class_name, confidence=confidence, device=device
        )

    @mcp.tool()
    def image_edit_by_mask(
        job_id: str,
        input_path: str,
        instance_id: str,
        action: str,
        color: str = "#ff0000",
        composite_path: str | None = None,
        blur_radius: float = 12.0,
    ) -> dict[str, str]:
        """Edit only one segmented external-image instance by its returned instance_id."""
        return service.image_edit_by_mask(
            job_id,
            input_path,
            instance_id,
            action,
            color=color,
            composite_path=composite_path,
            blur_radius=blur_radius,
        )

    if settings.unsafe_python:

        @mcp.tool()
        def blender_run_python(job_id: str, code: str, timeout: float | None = None) -> dict[str, Any]:
            """Execute arbitrary Blender Python with Blender process privileges. Require per-call approval."""
            return service.blender_run_python(job_id, code, timeout)

    @mcp.resource("blender://capabilities")
    def capabilities() -> str:
        return json.dumps(CAPABILITIES | {"unsafe_python_enabled": settings.unsafe_python}, indent=2)

    @mcp.resource("blender://skills/{skill_name}")
    def skill(skill_name: str) -> str:
        path = repo_root / "skills" / skill_name / "SKILL.md"
        if not path.is_file():
            raise ValueError(f"Unknown Blender skill: {skill_name}")
        return path.read_text(encoding="utf-8")

    @mcp.resource("blender://jobs/{job_id}/manifest")
    def manifest(job_id: str) -> str:
        return json.dumps(service.store.load(job_id), indent=2)

    @mcp.resource("blender://jobs/{job_id}/artifacts")
    def artifacts(job_id: str) -> str:
        return json.dumps(service.store.load(job_id)["artifacts"], indent=2)

    @mcp.prompt()
    def create_model_workflow(request: str) -> str:
        return (
            f"Create or modify and export a Blender model for: {request}. "
            "Begin with job_create, use typed mesh/material/camera tools, inspect before exporting, "
            "and never call arbitrary Python unless explicitly approved."
        )

    @mcp.prompt()
    def product_render_workflow(request: str) -> str:
        return (
            f"Produce a product render for: {request}. Use camera_light_setup and material_create_assign, "
            "then render_still or render_turntable; keep artifacts in the job."
        )

    @mcp.prompt()
    def segment_edit_workflow(request: str) -> str:
        return (
            f"Edit an external image instance for: {request}. Use image_segment, choose an instance_id "
            "from its metadata, then call image_edit_by_mask. Do not claim it identifies a Blender object."
        )

    @mcp.prompt()
    def cryptomatte_workflow(request: str) -> str:
        return (
            f"Extract a known rendered scene object/material for: {request}. Inspect the job scene first, "
            "then call render_object_mask with the exact Blender name; use Cryptomatte instead of YOLO."
        )

    return mcp


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
