from __future__ import annotations

from collections import defaultdict
from statistics import mean

LabelKey = tuple[tuple[str, str], ...]


def _normalize_labels(labels: dict[str, str] | None) -> LabelKey:
    if not labels:
        return ()
    return tuple(sorted(labels.items()))


class MetricsRegistry:
    def __init__(self, namespace: str = "repolens") -> None:
        self.namespace = namespace
        self._counters: defaultdict[tuple[str, LabelKey], float] = defaultdict(float)
        self._histograms: defaultdict[tuple[str, LabelKey], list[float]] = defaultdict(list)

    def increment(self, name: str, amount: float = 1, labels: dict[str, str] | None = None) -> None:
        self._counters[(name, _normalize_labels(labels))] += amount

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        self._histograms[(name, _normalize_labels(labels))].append(value)

    def render_prometheus(self) -> str:
        lines: list[str] = []
        for (name, labels), value in sorted(self._counters.items()):
            lines.append(self._render_metric(name, value, labels))
        for (name, labels), values in sorted(self._histograms.items()):
            metric_name = f"{name}_count"
            lines.append(self._render_metric(metric_name, len(values), labels))
            lines.append(self._render_metric(f"{name}_sum", sum(values), labels))
            lines.append(self._render_metric(f"{name}_avg", mean(values), labels))
            lines.append(self._render_metric(f"{name}_p95", self._percentile(values, 95), labels))
        return "\n".join(lines) + "\n"

    def _render_metric(self, name: str, value: float, labels: LabelKey) -> str:
        full_name = f"{self.namespace}_{name}"
        if not labels:
            return f"{full_name} {value}"
        rendered_labels = ",".join(f'{key}="{val}"' for key, val in labels)
        return f"{full_name}{{{rendered_labels}}} {value}"

    @staticmethod
    def _percentile(values: list[float], percentile: int) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = max(
            0,
            min(
                len(sorted_values) - 1,
                round((percentile / 100) * (len(sorted_values) - 1)),
            ),
        )
        return sorted_values[index]
