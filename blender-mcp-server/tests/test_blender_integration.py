from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import Image

from blender_mcp.blender import BlenderExecutionError
from blender_mcp.config import Settings
from blender_mcp.service import BlenderMCPService


BLENDER = shutil.which("blender")


@pytest.mark.skipif(BLENDER is None, reason="Blender is not installed on PATH")
def test_blender_create_render_and_export(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = BlenderMCPService(
        Settings(
            blender_bin=Path(BLENDER),
            workspace_root=workspace,
            output_root=tmp_path / "output",
            yolo_model=tmp_path / "yolo11n-seg.pt",
            default_timeout=90,
        )
    )

    health = service.blender_healthcheck()
    assert health["blender_compatible"] is True
    assert health["python_runner_available"] is True
    job_id = service.job_create()["job_id"]
    service.mesh_create(job_id, object_name="Product", primitive="cube")
    service.material_create_assign(job_id, "Product", "ProductMaterial", base_color=[0.2, 0.4, 0.8, 1.0])
    service.mesh_create(job_id, object_name="Marker", primitive="cube", location=[2.5, 0.0, 0.0], scale=[0.5, 0.5, 0.5])
    service.mesh_modify(
        job_id, "Product", "SOLIDIFY", parameters={"thickness": 0.02}, apply=True
    )
    service.mesh_repair(job_id, "Product", triangulate=True)
    service.camera_light_setup(
        job_id,
        camera_location=[4.0, -4.0, 3.0],
        camera_rotation=[1.109, 0.0, 0.785],
        light_location=[2.0, -2.0, 4.0],
    )
    render = service.render_still(job_id, "product.png", width=64, height=64)
    jpeg = service.render_still(job_id, "product.jpg", width=64, height=64)
    mask = service.render_object_mask(job_id, "Product", filename="product_mask.png", width=64, height=64)
    composite = service.compositor_apply(job_id, render["output_path"], "blur", filename="blurred.png")
    overlay = workspace / "overlay.png"
    Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(overlay)
    alpha_over = service.compositor_apply(
        job_id, render["output_path"], "alpha_over", filename="overlay.png", overlay_path="overlay.png"
    )
    masked = service.compositor_apply(
        job_id,
        render["output_path"],
        "mask_composite",
        filename="masked.png",
        overlay_path="overlay.png",
        mask_path=mask["output_path"],
    )
    stl = service.scene_export(job_id, "product.stl")
    glb = service.scene_export(job_id, "product.glb")
    usd = service.scene_export(job_id, "product.usdc")
    inspect = service.job_inspect(job_id)
    overlap = service.scene_check_overlap(job_id)
    service.object_define_anchor(job_id, "Product", "CENTER", location=[0.0, 0.0, 0.0])
    service.object_define_anchor(job_id, "Marker", "CENTER", location=[0.0, 0.0, 0.0])
    mate = service.object_mate(job_id, "Marker", "CENTER", "Product", "CENTER")
    fit = service.scene_verify_mechanical_fit(job_id)

    assert Path(render["output_path"]).is_file()
    assert Image.open(jpeg["output_path"]).format == "JPEG"
    assert Path(mask["output_path"]).is_file()
    assert Image.open(mask["output_path"]).convert("L").getbbox() is not None
    assert Path(composite["output_path"]).is_file()
    assert Path(alpha_over["output_path"]).is_file()
    assert Path(masked["output_path"]).is_file()
    assert Path(stl["output_path"]).is_file()
    assert Path(glb["output_path"]).is_file()
    assert Path(usd["output_path"]).is_file()
    assert any(obj["name"] == "Product" and "dimensions" in obj and "bounding_box" in obj for obj in inspect["scene"]["objects"])
    assert overlap["checked_objects"]
    assert mate["mate"]["target_object_name"] == "Product"
    assert fit["checked_objects"]
    assert fit["pairs"]
    versions = len(service.store.load(job_id)["versions"])
    with pytest.raises(ValueError):
        service.render_still(job_id, "mismatch.jpg", format="PNG")
    with pytest.raises(BlenderExecutionError):
        service.object_transform(job_id, "MissingObject", location=[0, 0, 0])
    assert len(service.store.load(job_id)["versions"]) == versions
