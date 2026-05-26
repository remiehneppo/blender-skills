from __future__ import annotations

from pathlib import Path

from PIL import Image

from blender_mcp.config import PathPolicy
from blender_mcp.jobs import JobStore
from blender_mcp.segmentation import ImageEditor, Segmenter
from blender_mcp.service import BlenderMCPService


def _source_image(path: Path) -> None:
    Image.new("RGBA", (4, 4), (10, 20, 30, 255)).save(path)


def test_segmentation_filters_instances_and_writes_artifacts(settings) -> None:
    source = settings.workspace_root / "scene.png"
    _source_image(source)
    paths = PathPolicy(settings)
    store = JobStore(paths)
    job_id = store.create()["job_id"]
    selected = Image.new("L", (4, 4), 0)
    selected.putpixel((1, 1), 255)

    def predict(*_args, **_kwargs):
        return [
            {"class_id": 0, "class_name": "cup", "confidence": 0.9, "bbox": [0, 0, 2, 2], "mask": selected},
            {"class_id": 0, "class_name": "cup", "confidence": 0.1, "bbox": [0, 0, 2, 2], "mask": selected},
            {"class_id": 1, "class_name": "book", "confidence": 0.8, "bbox": [2, 2, 4, 4], "mask": selected},
        ]

    result = Segmenter(settings, paths, store, predictor=predict).segment(job_id, "scene.png", class_name="cup")

    assert [item["class_name"] for item in result["instances"]] == ["cup"]
    assert Path(result["instances"][0]["mask_path"]).is_file()
    assert Path(result["instances"][0]["preview_path"]).is_file()


def test_image_actions_only_apply_inside_selected_mask(settings) -> None:
    source = settings.workspace_root / "scene.png"
    _source_image(source)
    paths = PathPolicy(settings)
    store = JobStore(paths)
    job_id = store.create()["job_id"]
    mask_path = store.artifact_path(job_id, "chosen_mask.png")
    mask = Image.new("L", (4, 4), 0)
    mask.putpixel((1, 1), 255)
    mask.save(mask_path)
    editor = ImageEditor(paths, store)

    recolor = editor.apply(job_id, "scene.png", str(mask_path), "recolor", color="#ff0000")
    recolored = Image.open(recolor["output_path"]).convert("RGBA")
    assert recolored.getpixel((1, 1))[:3] == (255, 0, 0)
    assert recolored.getpixel((0, 0))[:3] == (10, 20, 30)

    extracted = editor.apply(job_id, "scene.png", str(mask_path), "remove_background")
    transparent = Image.open(extracted["output_path"]).convert("RGBA")
    assert transparent.getpixel((1, 1))[3] == 255
    assert transparent.getpixel((0, 0))[3] == 0


def test_public_image_edit_selects_a_returned_instance_id(settings) -> None:
    source = settings.workspace_root / "scene.png"
    _source_image(source)
    service = BlenderMCPService(settings)
    job_id = service.store.create()["job_id"]
    mask = Image.new("L", (4, 4), 0)
    mask.putpixel((2, 2), 255)
    service.segmenter = Segmenter(
        settings,
        service.paths,
        service.store,
        predictor=lambda *_args, **_kwargs: [
            {"class_id": 0, "class_name": "cup", "confidence": 0.9, "bbox": [1, 1, 3, 3], "mask": mask}
        ],
    )

    instance = service.image_segment(job_id, "scene.png")["instances"][0]
    edited = service.image_edit_by_mask(job_id, "scene.png", instance["instance_id"], "recolor", color="#00ff00")
    result = Image.open(edited["output_path"]).convert("RGBA")

    assert result.getpixel((2, 2))[:3] == (0, 255, 0)
    assert result.getpixel((0, 0))[:3] == (10, 20, 30)
