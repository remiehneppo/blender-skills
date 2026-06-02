from __future__ import annotations

from blender_mcp.bbox import bbox_clearance, bbox_intersects, bbox_minimum_translation


def test_bbox_helpers_detect_overlap_and_translation() -> None:
    a = {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0], "center": [0.5, 0.5, 0.5]}
    b = {"min": [0.5, 0.25, 0.25], "max": [1.5, 0.75, 0.75], "center": [1.0, 0.5, 0.5]}

    assert bbox_intersects(a, b) is True
    assert bbox_minimum_translation(a, b)[0] != 0.0


def test_bbox_clearance_reports_separation() -> None:
    a = {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0], "center": [0.5, 0.5, 0.5]}
    b = {"min": [2.0, 0.0, 0.0], "max": [3.0, 1.0, 1.0], "center": [2.5, 0.5, 0.5]}

    assert bbox_intersects(a, b) is False
    assert bbox_clearance(a, b)[0] == 1.0
