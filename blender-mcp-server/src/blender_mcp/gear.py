from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class GearSpec:
    module: float
    teeth_count: int
    pressure_angle_deg: float
    width: float
    backlash: float = 0.0

    @property
    def pressure_angle_rad(self) -> float:
        return math.radians(self.pressure_angle_deg)

    @property
    def pitch_diameter(self) -> float:
        return self.module * self.teeth_count

    @property
    def pitch_radius(self) -> float:
        return self.pitch_diameter / 2.0

    @property
    def base_radius(self) -> float:
        return self.pitch_radius * math.cos(self.pressure_angle_rad)

    @property
    def addendum(self) -> float:
        return self.module

    @property
    def dedendum(self) -> float:
        return 1.25 * self.module

    @property
    def outer_radius(self) -> float:
        return self.pitch_radius + self.addendum

    @property
    def root_radius(self) -> float:
        return max(self.pitch_radius - self.dedendum, self.module * 0.25)

    @property
    def circular_pitch(self) -> float:
        return math.pi * self.module

    @property
    def tooth_thickness(self) -> float:
        return max(self.circular_pitch / 2.0 - self.backlash / 2.0, self.module * 0.05)

    def as_dict(self) -> dict[str, float]:
        return {
            "module": self.module,
            "teeth_count": self.teeth_count,
            "pressure_angle_deg": self.pressure_angle_deg,
            "pressure_angle_rad": self.pressure_angle_rad,
            "width": self.width,
            "backlash": self.backlash,
            "pitch_diameter": self.pitch_diameter,
            "pitch_radius": self.pitch_radius,
            "base_radius": self.base_radius,
            "addendum": self.addendum,
            "dedendum": self.dedendum,
            "outer_radius": self.outer_radius,
            "root_radius": self.root_radius,
            "circular_pitch": self.circular_pitch,
            "tooth_thickness": self.tooth_thickness,
        }


def gear_spec(module: float, teeth_count: int, pressure_angle: float, width: float, backlash: float = 0.0) -> GearSpec:
    if module <= 0:
        raise ValueError("module must be positive")
    if teeth_count < 3:
        raise ValueError("teeth_count must be at least 3")
    if width <= 0:
        raise ValueError("width must be positive")
    return GearSpec(
        module=float(module),
        teeth_count=int(teeth_count),
        pressure_angle_deg=float(pressure_angle),
        width=float(width),
        backlash=float(backlash),
    )


def gear_profile_points(spec: GearSpec, samples_per_flank: int = 8, tip_segments: int = 4) -> list[tuple[float, float]]:
    if samples_per_flank < 2:
        raise ValueError("samples_per_flank must be at least 2")
    if tip_segments < 2:
        raise ValueError("tip_segments must be at least 2")

    pitch_angle = 2.0 * math.pi / spec.teeth_count
    half_tooth_angle = pitch_angle / 2.0
    pitch_inv = _inv(math.acos(min(1.0, max(0.0, spec.base_radius / spec.pitch_radius))))
    flank_rotation_right = half_tooth_angle - pitch_inv
    flank_rotation_left = -half_tooth_angle + pitch_inv

    points: list[tuple[float, float]] = []
    for tooth_index in range(spec.teeth_count):
        center_angle = tooth_index * pitch_angle
        right_root = _polar(spec.root_radius, center_angle - half_tooth_angle)
        if not points:
            points.append(right_root)

        flank = _involute_flank(spec, samples_per_flank)
        points.extend(_rotate_points(flank, center_angle + flank_rotation_right)[1:])

        tip_start = _rotate_point((spec.outer_radius, 0.0), center_angle + flank_rotation_right)
        tip_end = _rotate_point((spec.outer_radius, 0.0), center_angle + flank_rotation_left)
        points.extend(_arc_points(spec.outer_radius, tip_start, tip_end, center_angle, tip_segments)[1:])

        left_flank = [(x, -y) for x, y in flank]
        points.extend(_rotate_points(left_flank, center_angle + flank_rotation_left)[1:])

        points.append(_polar(spec.root_radius, center_angle + half_tooth_angle))
    return _dedupe_points(points)


def _inv(alpha: float) -> float:
    return math.tan(alpha) - alpha


def _polar(radius: float, angle: float) -> tuple[float, float]:
    return radius * math.cos(angle), radius * math.sin(angle)


def _rotate_point(point: tuple[float, float], angle: float) -> tuple[float, float]:
    x, y = point
    cos_angle = math.cos(angle)
    sin_angle = math.sin(angle)
    return (x * cos_angle - y * sin_angle, x * sin_angle + y * cos_angle)


def _rotate_points(points: Iterable[tuple[float, float]], angle: float) -> list[tuple[float, float]]:
    return [_rotate_point(point, angle) for point in points]


def _involute_flank(spec: GearSpec, samples_per_flank: int) -> list[tuple[float, float]]:
    if spec.base_radius <= 0:
        return [_polar(spec.root_radius, 0.0), _polar(spec.outer_radius, 0.0)]
    max_param = math.sqrt(max((spec.outer_radius / spec.base_radius) ** 2 - 1.0, 0.0))
    if max_param == 0.0:
        return [_polar(spec.root_radius, 0.0), _polar(spec.outer_radius, 0.0)]
    return [
        (
            spec.base_radius * (math.cos(parameter) + parameter * math.sin(parameter)),
            spec.base_radius * (math.sin(parameter) - parameter * math.cos(parameter)),
        )
        for parameter in [index * max_param / (samples_per_flank - 1) for index in range(samples_per_flank)]
    ]


def _arc_points(
    radius: float, start: tuple[float, float], end: tuple[float, float], center_angle: float, segments: int
) -> list[tuple[float, float]]:
    start_angle = math.atan2(start[1], start[0])
    end_angle = math.atan2(end[1], end[0])
    if end_angle <= start_angle:
        end_angle += 2.0 * math.pi
    step = (end_angle - start_angle) / segments
    return [_polar(radius, start_angle + index * step) for index in range(segments + 1)]


def _dedupe_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    deduped: list[tuple[float, float]] = []
    for point in points:
        if not deduped or _distance(deduped[-1], point) > 1e-9:
            deduped.append(point)
    if len(deduped) > 1 and _distance(deduped[0], deduped[-1]) <= 1e-9:
        deduped.pop()
    return deduped


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
