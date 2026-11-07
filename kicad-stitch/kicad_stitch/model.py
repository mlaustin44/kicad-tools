"""Serializable inputs and results shared by the CLI and future GUI clients."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import math
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Signal:
    name: str = "signal"
    nets: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    mode: str = "fence"
    differential: bool = False
    offset_mm: float = 1.0
    pitch_mm: float | None = None

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("Signal name must be nonempty")
        for key in ("nets", "references"):
            values = getattr(self, key)
            if not isinstance(values, (tuple, list)) or not all(isinstance(v, str) and v for v in values):
                raise ValueError(f"Signal {key} must be an array of nonempty strings")
        if self.mode not in {"fence", "transitions"}:
            raise ValueError("Signal mode must be fence or transitions")
        if not isinstance(self.differential, bool):
            raise ValueError("Signal differential must be true or false")
        for key in ("offset_mm", "pitch_mm"):
            value = getattr(self, key)
            if value is None and key == "pitch_mm":
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Signal {key} must be finite and positive")


@dataclass(frozen=True)
class Settings:
    net: str = "GND"
    diameter_mm: float = 0.6
    drill_mm: float = 0.3
    allow_annular_width_warnings: bool = True
    clearance_mm: float = 0.2
    edge_clearance_mm: float = 0.3
    component_clearance_mm: float = 0.25
    min_spacing_mm: float = 1.0
    pitch_mm: float | None = None
    max_frequency_hz: float | None = None
    rise_time_ns: float | None = None
    epsilon_r: float = 4.3
    wavelength_divisor: float = 20.0
    perimeter_offset_mm: float = 1.0
    perimeter: bool = True
    islands: bool = True
    grid: bool = True
    fingers: bool = True
    auto_pairs: bool = True
    pair_fences: bool = False
    signal_offset_mm: float = 1.0
    neck_width_mm: float = 1.5
    max_vias: int = 5000
    max_samples: int = 250000
    anchors_mm: tuple[tuple[float, float], ...] = ()
    exclusions_mm: tuple[tuple[float, float, float, float], ...] = ()
    signals: tuple[Signal, ...] = ()

    def __post_init__(self):
        booleans = {"perimeter", "islands", "grid", "fingers", "auto_pairs", "pair_fences",
                    "allow_annular_width_warnings"}
        for key in booleans:
            if not isinstance(getattr(self, key), bool):
                raise ValueError(f"{key} must be true or false")
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name.endswith(("_mm", "_hz", "_ns")) and f.name not in {"anchors_mm", "exclusions_mm"}:
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                          or not math.isfinite(value) or value <= 0):
                    raise ValueError(f"{f.name} must be finite and positive")
        if not isinstance(self.net, str) or not self.net:
            raise ValueError("net must be nonempty")
        if self.drill_mm >= self.diameter_mm:
            raise ValueError("drill_mm must be smaller than diameter_mm")
        for name in ("max_vias", "max_samples"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("epsilon_r", "wavelength_divisor"):
            v = getattr(self, name)
            if not isinstance(v, (float, int)) or isinstance(v, bool) or not math.isfinite(v) or v < 1:
                raise ValueError(f"{name} must be finite and at least 1")
        for key, size in (("anchors_mm", 2), ("exclusions_mm", 4)):
            for coordinates in getattr(self, key):
                if len(coordinates) != size or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in coordinates):
                    raise ValueError(f"{key} needs finite {size}-coordinate entries")
                if size == 4 and (coordinates[0] >= coordinates[2] or coordinates[1] >= coordinates[3]):
                    raise ValueError("exclusions_mm needs [min_x, min_y, max_x, max_y]")
        for s in self.signals:
            if not isinstance(s, Signal) or not (s.nets or s.references):
                raise ValueError("Each signal needs nets/references and mode fence or transitions")

    def to_dict(self):
        return asdict(self)


def load_settings(path: Path | None) -> Settings:
    if path is None:
        return Settings()
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    unknown = set(data) - {"stitch", "signal"}
    if unknown:
        raise ValueError(f"Unknown TOML sections: {', '.join(sorted(unknown))}")
    values = dict(data.get("stitch", {}))
    signals = []
    for entry in data.get("signal", []):
        entry = dict(entry)
        for key in ("nets", "references"):
            if key in entry:
                if not isinstance(entry[key], list) or not all(isinstance(x, str) for x in entry[key]):
                    raise ValueError(f"signal.{key} must be an array of strings")
                entry[key] = tuple(entry[key])
        signals.append(Signal(**entry))
    values["signals"] = tuple(signals)
    for key in ("anchors_mm", "exclusions_mm"):
        if key in values:
            values[key] = tuple(tuple(x) for x in values[key])
    return Settings(**values)


@dataclass
class Candidate:
    x: float
    y: float
    rule: str
    reason: str
    layers: list[str]
    uuid: str | None = None


@dataclass
class Plan:
    schema_version: int = 1
    candidates: list[Candidate] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)
    validation: dict = field(default_factory=lambda: {"status": "geometry_only"})

    def to_dict(self):
        return asdict(self)
