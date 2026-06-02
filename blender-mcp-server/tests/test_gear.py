from __future__ import annotations

from blender_mcp.gear import gear_profile_points, gear_spec


def test_gear_spec_computes_geometry() -> None:
    gear = gear_spec(2.0, 20, 20.0, 5.0, backlash=0.1)

    assert gear.pitch_diameter == 40.0
    assert gear.base_radius > 0
    assert gear.outer_radius > gear.pitch_radius
    assert gear.tooth_thickness > 0


def test_gear_profile_points_are_closed_and_nontrivial() -> None:
    gear = gear_spec(2.0, 12, 20.0, 4.0)
    points = gear_profile_points(gear)

    assert len(points) > 10
    assert points[0] != points[-1]
