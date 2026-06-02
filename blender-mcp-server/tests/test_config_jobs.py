from __future__ import annotations

from pathlib import Path
import json

import pytest

from blender_mcp.config import PathPolicy, PathValidationError
from blender_mcp.jobs import JobNotFoundError, JobStore


def test_paths_confine_input_and_output(settings, tmp_path: Path) -> None:
    paths = PathPolicy(settings)
    source = settings.workspace_root / "input.obj"
    source.write_text("asset", encoding="utf-8")
    outside = tmp_path / "outside.obj"
    outside.write_text("asset", encoding="utf-8")

    assert paths.input_file("input.obj", {".obj"}) == source
    with pytest.raises(PathValidationError):
        paths.input_file(outside)
    with pytest.raises(PathValidationError):
        paths.output_path("..", "escape.png")
    artifact = paths.output_root / "artifacts" / "render.png"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"png")
    assert paths.existing_output_file(Path("artifacts/render.png")) == artifact


def test_job_scene_commits_are_versioned_and_failure_preserves_current(settings) -> None:
    store = JobStore(PathPolicy(settings))
    manifest = store.create()
    job_id = manifest["job_id"]
    first = store.directory(job_id) / "first.blend"
    first.write_bytes(b"first")
    store.commit_scene(job_id, first, "init")
    store.record_failure(job_id, "mesh_create", "Blender exited")

    failed = store.load(job_id)
    assert failed["current_version"] == "scene_v0001.blend"
    assert len(failed["versions"]) == 1
    assert failed["operations"][-1]["status"] == "error"

    second = store.candidate_scene(job_id)
    second.write_bytes(b"second")
    store.commit_scene(job_id, second, "mesh_create")
    committed = store.load(job_id)
    assert committed["current_version"] == "scene_v0002.blend"
    assert (store.directory(job_id) / committed["current_version"]).read_bytes() == b"second"


def test_job_store_reports_missing_job_ids(settings) -> None:
    store = JobStore(PathPolicy(settings))

    with pytest.raises(JobNotFoundError, match="Unknown job_id"):
        store.load("missing")


def test_artifact_filename_rejects_path_separators(settings) -> None:
    store = JobStore(PathPolicy(settings))
    job_id = store.create()["job_id"]

    with pytest.raises(ValueError, match="path separators"):
        store.artifact_path(job_id, "../escape.png")


def test_job_store_tracks_anchors_and_mates(settings) -> None:
    store = JobStore(PathPolicy(settings))
    job_id = store.create()["job_id"]

    anchor = store.add_anchor(
        job_id,
        "GearA",
        "SHAFT_CENTER",
        [0.0, 0.0, 0.0],
        normal=[0.0, 0.0, 1.0],
        up=[1.0, 0.0, 0.0],
        metadata={"purpose": "mate"},
    )
    mate = store.add_mate(job_id, "GearA", "SHAFT_CENTER", "GearB", "SHAFT_CENTER", metadata={"strategy": "snap"})

    manifest = store.load(job_id)
    assert manifest["anchors"][0]["anchor_name"] == "SHAFT_CENTER"
    assert manifest["mates"][0]["target_object_name"] == "GearB"
    assert store.find_anchor(job_id, "GearA", "SHAFT_CENTER") == anchor
    assert mate["metadata"]["strategy"] == "snap"


def test_job_store_loads_legacy_manifests_with_schema_migration(settings) -> None:
    store = JobStore(PathPolicy(settings))
    job_id = store.create()["job_id"]
    manifest_path = store.directory(job_id) / "manifest.json"
    legacy = {
        "job_id": job_id,
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
        "current_version": None,
        "versions": [],
        "artifacts": [],
        "anchors": [
            {
                "object_name": "GearA",
                "anchor_name": "SHAFT_CENTER",
                "location": [0.0, 0.0, 0.0],
                "normal": None,
                "up": None,
                "metadata": {},
                "created_at": "2024-01-01T00:00:00+00:00",
            }
        ],
        "mates": [],
        "operations": [],
    }
    manifest_path.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = store.load(job_id)

    assert loaded["schema_version"] >= 2
    assert loaded["anchors_by_key"]["GearA::SHAFT_CENTER"]["anchor_name"] == "SHAFT_CENTER"
    assert loaded["mates_by_key"] == {}
