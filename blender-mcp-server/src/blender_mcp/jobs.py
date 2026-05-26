from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import PathPolicy


class JobNotFoundError(KeyError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, paths: PathPolicy):
        self.paths = paths
        self.paths.prepare_output_root()
        self._lock = threading.RLock()

    def create(self) -> dict[str, Any]:
        with self._lock:
            job_id = uuid.uuid4().hex
            directory = self.paths.output_path("jobs", job_id, mkdir=True)
            (directory / "artifacts").mkdir()
            (directory / "logs").mkdir()
            manifest: dict[str, Any] = {
                "job_id": job_id,
                "created_at": _now(),
                "updated_at": _now(),
                "current_version": None,
                "versions": [],
                "artifacts": [],
                "operations": [],
            }
            self._write_manifest(directory, manifest)
            return self.load(job_id)

    def directory(self, job_id: str) -> Path:
        if not job_id or not job_id.isalnum():
            raise JobNotFoundError(job_id)
        directory = self.paths.output_path("jobs", job_id)
        if not directory.is_dir():
            raise JobNotFoundError(job_id)
        return directory

    def load(self, job_id: str) -> dict[str, Any]:
        manifest_path = self.directory(job_id) / "manifest.json"
        with manifest_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def current_scene(self, job_id: str) -> Path | None:
        manifest = self.load(job_id)
        version = manifest.get("current_version")
        return self.directory(job_id) / version if version else None

    def candidate_scene(self, job_id: str) -> Path:
        manifest = self.load(job_id)
        number = len(manifest["versions"]) + 1
        return self.directory(job_id) / f"scene_v{number:04d}.blend.pending"

    def commit_scene(
        self, job_id: str, candidate: Path, operation: str, metadata: dict[str, Any] | None = None
    ) -> Path:
        with self._lock:
            manifest = self.load(job_id)
            number = len(manifest["versions"]) + 1
            filename = f"scene_v{number:04d}.blend"
            destination = self.directory(job_id) / filename
            if candidate.resolve() != destination.resolve():
                shutil.copy2(candidate, destination)
            manifest["versions"].append(
                {"version": number, "path": filename, "operation": operation, "created_at": _now()}
            )
            manifest["current_version"] = filename
            manifest["operations"].append(
                {"operation": operation, "status": "ok", "created_at": _now(), "metadata": metadata or {}}
            )
            manifest["updated_at"] = _now()
            self._write_manifest(self.directory(job_id), manifest)
            if candidate.name.endswith(".pending") and candidate.exists():
                candidate.unlink()
            return destination

    def record_failure(self, job_id: str, operation: str, message: str) -> None:
        with self._lock:
            manifest = self.load(job_id)
            manifest["operations"].append(
                {"operation": operation, "status": "error", "created_at": _now(), "message": message}
            )
            manifest["updated_at"] = _now()
            self._write_manifest(self.directory(job_id), manifest)

    def record_success(self, job_id: str, operation: str, metadata: dict[str, Any] | None = None) -> None:
        with self._lock:
            manifest = self.load(job_id)
            manifest["operations"].append(
                {"operation": operation, "status": "ok", "created_at": _now(), "metadata": metadata or {}}
            )
            manifest["updated_at"] = _now()
            self._write_manifest(self.directory(job_id), manifest)

    def artifact_path(self, job_id: str, filename: str) -> Path:
        if Path(filename).name != filename:
            raise ValueError("Artifact filename must not contain path separators")
        return self.directory(job_id) / "artifacts" / filename

    def add_artifact(self, job_id: str, kind: str, path: Path, metadata: dict[str, Any] | None = None) -> None:
        with self._lock:
            manifest = self.load(job_id)
            relative = str(path.relative_to(self.directory(job_id)))
            manifest["artifacts"].append(
                {"kind": kind, "path": relative, "created_at": _now(), "metadata": metadata or {}}
            )
            manifest["updated_at"] = _now()
            self._write_manifest(self.directory(job_id), manifest)

    @staticmethod
    def _write_manifest(directory: Path, manifest: dict[str, Any]) -> None:
        target = directory / "manifest.json"
        temporary = directory / "manifest.json.tmp"
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
        temporary.replace(target)
