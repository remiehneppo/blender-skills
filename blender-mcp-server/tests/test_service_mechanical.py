from __future__ import annotations

from blender_mcp.service import BlenderMCPService


class FakeExecutor:
    def __init__(self):
        self.calls: list[tuple[str, str, dict[str, object], bool]] = []

    def run(self, job_id: str, action: str, params: dict[str, object], *, mutate_scene: bool = True, **_: object):
        self.calls.append((job_id, action, params, mutate_scene))
        if action == "object_define_anchor":
            return {
                "scene": {"objects": []},
                "object_name": params["object_name"],
                "anchor_name": params["anchor_name"],
                "location": params.get("location") or [0.0, 0.0, 0.0],
                "normal": params.get("normal"),
                "up": params.get("up"),
                "metadata": params.get("metadata") or {},
            }
        if action == "object_mate":
            return {
                "scene": {"objects": []},
                "transform_matrix": [[1.0, 0.0, 0.0, 0.0]] * 4,
            }
        if action == "scene_check_overlap":
            return {"scene": {"objects": []}, "overlaps": []}
        if action == "scene_verify_mechanical_fit":
            return {"scene": {"objects": []}, "pairs": []}
        return {"scene": {"objects": []}}


def test_service_records_anchors_and_mates(settings) -> None:
    executor = FakeExecutor()
    service = BlenderMCPService(settings, executor=executor)
    job_id = service.store.create()["job_id"]

    defined = service.object_define_anchor(
        job_id,
        "GearA",
        "SHAFT_CENTER",
        location=[0.0, 0.0, 0.0],
        normal=[0.0, 0.0, 1.0],
        up=[1.0, 0.0, 0.0],
        purpose="mate",
    )
    assert defined["anchor"]["anchor_name"] == "SHAFT_CENTER"
    assert service.store.find_anchor(job_id, "GearA", "SHAFT_CENTER") is not None

    service.store.add_anchor(job_id, "GearB", "SHAFT_CENTER", [1.0, 0.0, 0.0])
    mated = service.object_mate(job_id, "GearA", "SHAFT_CENTER", "GearB", "SHAFT_CENTER")

    assert mated["mate"]["target_object_name"] == "GearB"
    assert service.store.load(job_id)["mates"][0]["anchor_name"] == "SHAFT_CENTER"


def test_service_exposes_mechanical_helpers(settings) -> None:
    executor = FakeExecutor()
    service = BlenderMCPService(settings, executor=executor)
    job_id = service.store.create()["job_id"]

    service.mesh_create_gear(job_id, "Gear", 1.0, 8, 0.2)
    service.mesh_create_joint(job_id, "Joint", "male", 0.01, 0.02)
    service.scene_check_overlap(job_id)
    service.scene_verify_mechanical_fit(job_id, minimum_clearance_mm=0.0)

    actions = [call[1] for call in executor.calls]
    assert "mesh_create_gear" in actions
    assert "mesh_create_joint" in actions
    assert "scene_check_overlap" in actions
    assert "scene_verify_mechanical_fit" in actions
