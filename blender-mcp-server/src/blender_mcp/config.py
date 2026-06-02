from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(RuntimeError):
    pass


class PathValidationError(ValueError):
    pass


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _split_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    items: list[str] = []
    seen: set[str] = set()
    for chunk in value.replace(";", ",").split(","):
        for item in chunk.split():
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                items.append(cleaned)
    return tuple(items)


@dataclass(frozen=True)
class Settings:
    blender_bin: Path
    workspace_root: Path
    output_root: Path
    yolo_model: Path
    blender_addons: tuple[str, ...] = ()
    yolo_device: str | None = None
    unsafe_python: bool = False
    default_timeout: float = 120.0

    @classmethod
    def from_env(cls) -> "Settings":
        required = ("BLENDER_BIN", "BLENDER_MCP_WORKSPACE_ROOT")
        missing = [key for key in required if not os.environ.get(key)]
        if missing:
            raise ConfigurationError(f"Missing required environment variables: {', '.join(missing)}")
        model = os.environ.get("BLENDER_MCP_YOLO_MODEL", "yolo11n-seg.pt")
        output_root = os.environ.get("BLENDER_MCP_OUTPUT_ROOT")
        return cls(
            blender_bin=Path(os.environ["BLENDER_BIN"]).expanduser().resolve(),
            blender_addons=_split_list(os.environ.get("BLENDER_MCP_BLENDER_ADDONS")),
            workspace_root=Path(os.environ["BLENDER_MCP_WORKSPACE_ROOT"]).expanduser().resolve(),
            output_root=Path(output_root).expanduser().resolve() if output_root else Path.cwd().resolve(),
            yolo_model=Path(model).expanduser().resolve(),
            yolo_device=os.environ.get("BLENDER_MCP_YOLO_DEVICE"),
            unsafe_python=os.environ.get("BLENDER_MCP_ENABLE_UNSAFE_PYTHON") == "1",
            default_timeout=float(os.environ.get("BLENDER_MCP_TIMEOUT", "120")),
        )


class PathPolicy:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.workspace_root = settings.workspace_root.resolve()
        self.output_root = settings.output_root.resolve()

    def prepare_output_root(self) -> Path:
        if self.output_root.exists() and not self.output_root.is_dir():
            raise PathValidationError(f"Output root is not a directory: {self.output_root}")
        self.output_root.mkdir(parents=True, exist_ok=True)
        return self.output_root

    def input_file(self, value: str | Path, suffixes: set[str] | None = None) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.workspace_root / path
        path = path.resolve()
        if not _within(path, self.workspace_root):
            raise PathValidationError(f"Input path is outside workspace root: {path}")
        if not path.is_file():
            raise PathValidationError(f"Input file does not exist: {path}")
        if suffixes and path.suffix.lower() not in suffixes:
            raise PathValidationError(f"Unsupported file extension: {path.suffix}")
        return path

    def output_path(self, *parts: str, mkdir: bool = False) -> Path:
        path = self.output_root.joinpath(*parts).resolve()
        if not _within(path, self.output_root):
            raise PathValidationError(f"Output path is outside output root: {path}")
        if mkdir:
            if path.exists() and not path.is_dir():
                raise PathValidationError(f"Output path is not a directory: {path}")
            path.mkdir(parents=True, exist_ok=True)
        return path

    def existing_output_file(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.output_root / path
        path = path.resolve()
        if not _within(path, self.output_root):
            raise PathValidationError(f"Artifact path is outside output root: {path}")
        if not path.is_file():
            raise PathValidationError(f"Artifact file does not exist: {path}")
        return path
