from __future__ import annotations

from blender_mcp.joints import joint_profile_points, joint_spec


def test_joint_spec_computes_geometry() -> None:
    joint = joint_spec("female", 10.0, 20.0, clearance=0.2, wall_thickness=1.0)

    assert joint.inner_radius == 5.2
    assert joint.outer_radius > joint.inner_radius


def test_joint_profile_points_respect_segment_count() -> None:
    joint = joint_spec("male", 10.0, 20.0)
    points = joint_profile_points(joint, segments=16)

    assert len(points) == 16
