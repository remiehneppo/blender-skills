from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JointSpec:
    kind: str
    diameter: float
    length: float
    clearance: float = 0.0
    wall_thickness: float = 0.0

    @property
    def radius(self) -> float:
        return self.diameter / 2.0

    @property
    def inner_radius(self) -> float:
        if self.kind == "female":
            return self.radius + self.clearance
        return max(self.radius - self.clearance, self.radius * 0.1)

    @property
    def outer_radius(self) -> float:
        if self.kind == "female":
            return self.inner_radius + max(self.wall_thickness, self.radius * 0.15)
        return self.radius

    def as_dict(self) -> dict[str, float | str]:
        return {
            "kind": self.kind,
            "diameter": self.diameter,
            "length": self.length,
            "clearance": self.clearance,
            "wall_thickness": self.wall_thickness,
            "radius": self.radius,
            "inner_radius": self.inner_radius,
            "outer_radius": self.outer_radius,
        }


def joint_spec(
    kind: str,
    diameter: float,
    length: float,
    *,
    clearance: float = 0.0,
    wall_thickness: float = 0.0,
) -> JointSpec:
    if kind not in {"male", "female", "shaft", "hole", "bearing"}:
        raise ValueError(f"Unsupported joint kind: {kind}")
    if diameter <= 0:
        raise ValueError("diameter must be positive")
    if length <= 0:
        raise ValueError("length must be positive")
    normalized = "female" if kind in {"female", "hole", "bearing"} else "male"
    return JointSpec(
        kind=normalized,
        diameter=float(diameter),
        length=float(length),
        clearance=float(clearance),
        wall_thickness=float(wall_thickness),
    )


def joint_profile_points(spec: JointSpec, segments: int = 32) -> list[tuple[float, float]]:
    import math

    if segments < 8:
        raise ValueError("segments must be at least 8")
    radius = spec.outer_radius if spec.kind == "female" else spec.radius
    return [(radius * math.cos(index * 2.0 * math.pi / segments), radius * math.sin(index * 2.0 * math.pi / segments)) for index in range(segments)]
