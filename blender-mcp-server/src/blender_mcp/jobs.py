from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import PathPolicy

SCHEMA_VERSION = 2


class JobNotFoundError(KeyError):
    def __init__(self, job_id: str):
        super().__init__(f"Unknown job_id: {job_id}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _anchor_key(object_name: str, anchor_name: str) -> str:
    return f"{object_name}::{anchor_name}"


def _mate_key(
    object_name: str,
    anchor_name: str,
    target_object_name: str,
    target_anchor_name: str,
) -> str:
    return f"{object_name}::{anchor_name}->{target_object_name}::{target_anchor_name}"


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value]
    if isinstance(value, dict):
        return [dict(item) for item in value.values()]
    return []


def _as_index(value: Any, key_fn) -> dict[str, dict[str, Any]]:
    if isinstance(value, dict):
        return {str(key): dict(item) for key, item in value.items()}
    index: dict[str, dict[str, Any]] = {}
    for item in _as_list(value):
        try:
            index[key_fn(item)] = item
        except KeyError:
            continue
    return index


def _normalize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(manifest)
    normalized["schema_version"] = int(normalized.get("schema_version") or SCHEMA_VERSION)
    normalized.setdefault("job_id", "")
    normalized.setdefault("created_at", _now())
    normalized.setdefault("updated_at", normalized["created_at"])
    normalized.setdefault("current_version", None)
    normalized["versions"] = list(normalized.get("versions", []))
    normalized["artifacts"] = [dict(item) for item in normalized.get("artifacts", [])]
    anchors = _as_list(normalized.get("anchors", []))
    mates = _as_list(normalized.get("mates", []))
    normalized["anchors"] = anchors
    normalized["anchors_by_key"] = _as_index(
        normalized.get("anchors_by_key", anchors), lambda item: _anchor_key(item["object_name"], item["anchor_name"])
    )
    normalized["mates"] = mates
    normalized["mates_by_key"] = _as_index(
        normalized.get("mates_by_key", mates),
        lambda item: _mate_key(
            item["object_name"],
            item["anchor_name"],
            item["target_object_name"],
            item["target_anchor_name"],
        ),
    )
    normalized["operations"] = [dict(item) for item in normalized.get("operations", [])]
    return normalized


class JobStore:
    def __init__(self, paths: PathPolicy):
        self.paths = paths
        self.paths.prepare_output_root()
        self._lock = threading.RLock()

    def create(self) -> dict[str, Any]:
        with self._lock:
            job_id = uuid.uuid4().hex
            directory = self.paths.output_path("jobs", job_id, mkdir=True)
            (directory / "artifacts").mkdir(parents=True, exist_ok=True)
            (directory / "logs").mkdir(parents=True, exist_ok=True)
            manifest: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "job_id": job_id,
                "created_at": _now(),
                "updated_at": _now(),
                "current_version": None,
                "versions": [],
                "artifacts": [],
                "anchors": [],
                "anchors_by_key": {},
                "mates": [],
                "mates_by_key": {},
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
            return _normalize_manifest(json.load(handle))

    def current_scene(self, job_id: str) -> Path | None:
        manifest = self.load(job_id)
        version = manifest.get("current_version")
        if not version:
            return None
        scene = self.directory(job_id) / version
        return scene if scene.is_file() else None

    def candidate_scene(self, job_id: str) -> Path:
        manifest = self.load(job_id)
        number = len(manifest["versions"]) + 1
        return self.directory(job_id) / f"scene_v{number:04d}.blend.pending"

    def commit_scene(
        self, job_id: str, candidate: Path, operation: str, metadata: dict[str, Any] | None = None
    ) -> Path:
        with self._lock:
            if not candidate.is_file():
                raise FileNotFoundError(f"Candidate scene does not exist: {candidate}")
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
                {
                    "operation": operation,
                    "status": "ok",
                    "created_at": _now(),
                    "metadata": dict(metadata or {}),
                }
            )
            manifest["updated_at"] = _now()
            self._write_manifest(self.directory(job_id), manifest)
            if candidate.name.endswith(".pending") and candidate.exists():
                candidate.unlink()
            return destination

    def record_failure(
        self,
        job_id: str,
        operation: str,
        message: str,
        *,
        log_path: str | None = None,
        returncode: int | None = None,
    ) -> None:
        with self._lock:
            manifest = self.load(job_id)
            manifest["operations"].append(
                {
                    "operation": operation,
                    "status": "error",
                    "created_at": _now(),
                    "message": message,
                    "metadata": {
                        **({"log_path": log_path} if log_path else {}),
                        **({"returncode": returncode} if returncode is not None else {}),
                    },
                }
            )
            manifest["updated_at"] = _now()
            self._write_manifest(self.directory(job_id), manifest)

    def record_success(
        self,
        job_id: str,
        operation: str,
        metadata: dict[str, Any] | None = None,
        *,
        log_path: str | None = None,
        returncode: int | None = None,
    ) -> None:
        with self._lock:
            manifest = self.load(job_id)
            details = dict(metadata or {})
            if log_path:
                details = {**details, "log_path": log_path}
            if returncode is not None:
                details = {**details, "returncode": returncode}
            manifest["operations"].append(
                {"operation": operation, "status": "ok", "created_at": _now(), "metadata": details}
            )
            manifest["updated_at"] = _now()
            self._write_manifest(self.directory(job_id), manifest)

    def artifact_path(self, job_id: str, filename: str) -> Path:
        artifact = Path(filename)
        if artifact.name != filename:
            raise ValueError("Artifact filename must not contain path separators")
        return self.directory(job_id) / "artifacts" / artifact.name

    def add_artifact(self, job_id: str, kind: str, path: Path, metadata: dict[str, Any] | None = None) -> None:
        with self._lock:
            manifest = self.load(job_id)
            relative = str(path.relative_to(self.directory(job_id)))
            manifest["artifacts"].append(
                {"kind": kind, "path": relative, "created_at": _now(), "metadata": metadata or {}}
            )
            manifest["updated_at"] = _now()
            self._write_manifest(self.directory(job_id), manifest)

    def add_anchor(
        self,
        job_id: str,
        object_name: str,
        anchor_name: str,
        location: list[float],
        *,
        normal: list[float] | None = None,
        up: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            manifest = self.load(job_id)
            record = {
                "object_name": object_name,
                "anchor_name": anchor_name,
                "location": [float(value) for value in location],
                "normal": [float(value) for value in normal] if normal is not None else None,
                "up": [float(value) for value in up] if up is not None else None,
                "metadata": dict(metadata or {}),
                "created_at": _now(),
            }
            key = _anchor_key(object_name, anchor_name)
            manifest["anchors"] = [
                item
                for item in manifest.get("anchors", [])
                if _anchor_key(item["object_name"], item["anchor_name"]) != key
            ]
            manifest.setdefault("anchors_by_key", {})
            manifest["anchors_by_key"][key] = record
            manifest["anchors"].append(record)
            manifest["updated_at"] = _now()
            self._write_manifest(self.directory(job_id), manifest)
            return record

    def add_mate(
        self,
        job_id: str,
        object_name: str,
        anchor_name: str,
        target_object_name: str,
        target_anchor_name: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            manifest = self.load(job_id)
            record = {
                "object_name": object_name,
                "anchor_name": anchor_name,
                "target_object_name": target_object_name,
                "target_anchor_name": target_anchor_name,
                "metadata": dict(metadata or {}),
                "created_at": _now(),
            }
            key = _mate_key(object_name, anchor_name, target_object_name, target_anchor_name)
            manifest.setdefault("mates_by_key", {})
            manifest["mates_by_key"][key] = record
            manifest["mates"] = [
                item
                for item in manifest.get("mates", [])
                if _mate_key(
                    item["object_name"],
                    item["anchor_name"],
                    item["target_object_name"],
                    item["target_anchor_name"],
                )
                != key
            ]
            manifest["mates"].append(record)
            manifest["updated_at"] = _now()
            self._write_manifest(self.directory(job_id), manifest)
            return record

    def find_anchor(self, job_id: str, object_name: str, anchor_name: str) -> dict[str, Any] | None:
        manifest = self.load(job_id)
        return manifest.get("anchors_by_key", {}).get(_anchor_key(object_name, anchor_name))

    @staticmethod
    def _write_manifest(directory: Path, manifest: dict[str, Any]) -> None:
        target = directory / "manifest.json"
        temporary = directory / "manifest.json.tmp"
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
        temporary.replace(target)
