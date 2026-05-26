from __future__ import annotations

from pathlib import Path

import pytest

from blender_mcp.config import PathPolicy, PathValidationError
from blender_mcp.jobs import JobStore


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
