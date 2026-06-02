from __future__ import annotations

from typing import Iterable


def bbox_from_corners(corners: Iterable[Iterable[float]]) -> dict[str, list[float]]:
    points = [tuple(float(value) for value in corner) for corner in corners]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    zs = [point[2] for point in points]
    minimum = [min(xs), min(ys), min(zs)]
    maximum = [max(xs), max(ys), max(zs)]
    return {
        "min": minimum,
        "max": maximum,
        "dimensions": [maximum[index] - minimum[index] for index in range(3)],
        "center": [(minimum[index] + maximum[index]) / 2.0 for index in range(3)],
    }


def bbox_intersects(a: dict[str, list[float]], b: dict[str, list[float]]) -> bool:
    for index in range(3):
        if a["max"][index] < b["min"][index] or b["max"][index] < a["min"][index]:
            return False
    return True


def bbox_overlap(a: dict[str, list[float]], b: dict[str, list[float]]) -> list[float]:
    overlaps: list[float] = []
    for index in range(3):
        overlaps.append(min(a["max"][index], b["max"][index]) - max(a["min"][index], b["min"][index]))
    return overlaps


def bbox_clearance(a: dict[str, list[float]], b: dict[str, list[float]]) -> list[float]:
    clearances: list[float] = []
    for index in range(3):
        if a["max"][index] < b["min"][index]:
            clearances.append(b["min"][index] - a["max"][index])
        elif b["max"][index] < a["min"][index]:
            clearances.append(a["min"][index] - b["max"][index])
        else:
            clearances.append(0.0)
    return clearances


def bbox_minimum_translation(a: dict[str, list[float]], b: dict[str, list[float]]) -> list[float]:
    overlaps = bbox_overlap(a, b)
    axis = min(range(3), key=lambda index: abs(overlaps[index]))
    direction = 1.0 if a["center"][axis] <= b["center"][axis] else -1.0
    vector = [0.0, 0.0, 0.0]
    vector[axis] = overlaps[axis] * direction
    return vector
