from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RatingCategory:
    key: str
    label: str


RATING_CATEGORIES: tuple[RatingCategory, ...] = (
    RatingCategory("story", "Story"),
    RatingCategory("characters", "Characters"),
    RatingCategory("dialogue", "Dialogue"),
    RatingCategory("visuals", "Visuals"),
    RatingCategory("soundtrack", "Soundtrack"),
    RatingCategory("worldbuilding", "Worldbuilding"),
    RatingCategory("direction", "Direction"),
    RatingCategory("pacing", "Pacing"),
    RatingCategory("emotional_impact", "Emotional Impact"),
    RatingCategory("enjoyment", "Enjoyment"),
)

RATING_CATEGORY_KEYS = tuple(category.key for category in RATING_CATEGORIES)


def rating_total(scores: dict[str, float]) -> float:
    """Return the /100 total for the configured ten-category system."""
    return round(sum(float(scores.get(key, 0.0)) for key in RATING_CATEGORY_KEYS), 1)
