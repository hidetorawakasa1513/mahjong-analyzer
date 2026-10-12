from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricSummary:
    total_reviewed: int
    total_matches: int
    comparable_decisions: int
    low_probability_decisions: int
    rating_values: tuple[float, ...]

    @property
    def ai_agreement_rate(self) -> float | None:
        if self.total_reviewed == 0:
            return None
        return self.total_matches / self.total_reviewed

    def low_recommendation_rate(self) -> float | None:
        if self.comparable_decisions == 0:
            return None
        return self.low_probability_decisions / self.comparable_decisions


def calculate_low_probability_rate(
    probabilities: list[float | None], threshold: float = 0.05
) -> tuple[int, int, float | None]:
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    comparable = [probability for probability in probabilities if probability is not None]
    low = sum(probability < threshold for probability in comparable)
    return low, len(comparable), low / len(comparable) if comparable else None
