from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageColor, ImageFilter

from .config import PathPolicy, Settings
from .jobs import JobStore


class SegmentationUnavailableError(RuntimeError):
    pass


class Segmenter:
    def __init__(
        self,
        settings: Settings,
        paths: PathPolicy,
        store: JobStore,
        predictor: Callable[..., list[dict[str, Any]]] | None = None,
    ):
        self.settings = settings
        self.paths = paths
        self.store = store
        self._predictor = predictor

    def _predict(self, input_path: Path, confidence: float, device: str | None) -> list[dict[str, Any]]:
        if self._predictor:
            return self._predictor(str(input_path), confidence=confidence, device=device)
        if not self.settings.yolo_model.is_file():
            raise SegmentationUnavailableError(
                f"YOLO model is not present at {self.settings.yolo_model}. "
                "Set up weights before invoking image_segment."
            )
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise SegmentationUnavailableError(
                "Install blender-mcp-server[segmentation] to enable YOLO segmentation."
            ) from exc
        result = YOLO(str(self.settings.yolo_model)).predict(
            source=str(input_path), conf=confidence, device=device, verbose=False
        )[0]
        if result.masks is None:
            return []
        detected = []
        for index, box in enumerate(result.boxes):
            class_id = int(box.cls.item())
            detected.append(
                {
                    "class_id": class_id,
                    "class_name": result.names[class_id],
                    "confidence": float(box.conf.item()),
                    "bbox": [float(value) for value in box.xyxy[0].tolist()],
                    "mask": result.masks.data[index].cpu().numpy(),
                }
            )
        return detected

    def segment(
        self,
        job_id: str,
        input_path: str,
        *,
        class_name: str | None = None,
        confidence: float = 0.25,
        device: str | None = None,
    ) -> dict[str, Any]:
        source = self.paths.input_file(input_path, {".png", ".jpg", ".jpeg", ".webp"})
        image = Image.open(source).convert("RGBA")
        instances = []
        for raw in self._predict(source, confidence, device or self.settings.yolo_device):
            if raw["confidence"] < confidence or (class_name and raw["class_name"] != class_name):
                continue
            instance_id = f"instance_{len(instances):04d}"
            mask_path = self.store.artifact_path(job_id, f"{instance_id}_mask.png")
            preview_path = self.store.artifact_path(job_id, f"{instance_id}_preview.png")
            mask = raw["mask"]
            if isinstance(mask, Image.Image):
                mask_image = mask.convert("L")
            else:
                mask_image = Image.fromarray((mask * 255).astype("uint8"), mode="L")
            mask_image = mask_image.resize(image.size, Image.Resampling.NEAREST)
            mask_image.save(mask_path)
            overlay = Image.new("RGBA", image.size, (0, 120, 255, 0))
            overlay.putalpha(mask_image.point(lambda value: min(150, value)))
            Image.alpha_composite(image, overlay).save(preview_path)
            metadata = {
                "instance_id": instance_id,
                "class_id": raw["class_id"],
                "class_name": raw["class_name"],
                "confidence": raw["confidence"],
                "bbox": raw["bbox"],
                "mask_path": str(mask_path),
                "preview_path": str(preview_path),
            }
            self.store.add_artifact(job_id, "instance_mask", mask_path, metadata)
            self.store.add_artifact(job_id, "segmentation_preview", preview_path, {"instance_id": instance_id})
            instances.append(metadata)
        return {"input_path": str(source), "instances": instances}


class ImageEditor:
    def __init__(self, paths: PathPolicy, store: JobStore):
        self.paths = paths
        self.store = store

    def apply(
        self,
        job_id: str,
        input_path: str,
        mask_path: str,
        action: str,
        *,
        color: str = "#ff0000",
        composite_path: str | None = None,
        blur_radius: float = 12,
    ) -> dict[str, str]:
        source = self.paths.input_file(input_path, {".png", ".jpg", ".jpeg", ".webp"})
        mask = Image.open(self.paths.existing_output_file(mask_path)).convert("L")
        image = Image.open(source).convert("RGBA")
        if mask.size != image.size:
            mask = mask.resize(image.size, Image.Resampling.NEAREST)
        output = self.store.artifact_path(job_id, f"edit_{action}_{len(self.store.load(job_id)['artifacts']):04d}.png")
        if action in {"extract", "remove_background"}:
            result = image.copy()
            result.putalpha(mask)
        elif action == "blur_background":
            background = image.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            result = Image.composite(image, background, mask)
        elif action == "recolor":
            rgb = ImageColor.getrgb(color)
            tinted = Image.new("RGBA", image.size, (*rgb, 255))
            result = Image.composite(tinted, image, mask)
        elif action == "composite":
            if not composite_path:
                raise ValueError("composite_path is required for composite action")
            foreground = Image.open(
                self.paths.input_file(composite_path, {".png", ".jpg", ".jpeg", ".webp"})
            ).convert("RGBA")
            foreground = foreground.resize(image.size, Image.Resampling.LANCZOS)
            result = Image.composite(foreground, image, mask)
        else:
            raise ValueError(f"Unsupported image edit action: {action}")
        result.save(output)
        self.store.add_artifact(job_id, "image_edit", output, {"action": action, "mask_path": mask_path})
        return {"action": action, "output_path": str(output)}
