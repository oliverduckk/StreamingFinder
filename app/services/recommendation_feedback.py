from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.models.media import MediaFeatureProfile, RecommendationFeedbackEntry


@dataclass(slots=True)
class FeedbackTasteModel:
    """Small, deliberately conservative taste model learned from card reactions."""

    genre_weights: dict[int, float] = field(default_factory=dict)
    genre_names: dict[int, str] = field(default_factory=dict)
    keyword_weights: dict[int, float] = field(default_factory=dict)
    keyword_names: dict[int, str] = field(default_factory=dict)
    creator_weights: dict[str, float] = field(default_factory=dict)
    sample_size: int = 0


def feedback_signal(item: RecommendationFeedbackEntry) -> float:
    """Return a bounded -1..1 preference signal for one recommended title.

    Opening details is weak evidence, watchlisting is stronger positive evidence,
    and Not interested is strong negative evidence. Marking a title watched is
    deliberately neutral: it excludes the title but does not imply whether it was liked.
    """

    open_signal = min(0.24, item.open_count * 0.08)
    watchlist_signal = 0.62 if item.watchlist_count > 0 else 0.0
    negative_signal = 0.92 if item.not_interested_count > 0 else 0.0
    return max(-1.0, min(1.0, open_signal + watchlist_signal - negative_signal))


def build_feedback_taste_model(
    feedback: list[RecommendationFeedbackEntry],
    features_by_key: dict[tuple[str, int], MediaFeatureProfile],
) -> FeedbackTasteModel:
    signals = [
        (feedback_signal(item), features_by_key.get((item.media_type, item.tmdb_id)))
        for item in feedback
    ]
    usable = [
        (signal, feature)
        for signal, feature in signals
        if feature is not None and abs(signal) >= 0.05
    ]
    if not usable:
        return FeedbackTasteModel()

    genre_values: defaultdict[int, list[float]] = defaultdict(list)
    genre_names: dict[int, str] = {}
    keyword_values: defaultdict[int, list[float]] = defaultdict(list)
    keyword_names: dict[int, str] = {}
    creator_values: defaultdict[str, list[float]] = defaultdict(list)

    for signal, feature in usable:
        for genre_id, genre_name in zip(feature.genre_ids, feature.genre_names, strict=False):
            genre_values[genre_id].append(signal)
            genre_names[genre_id] = genre_name
        for keyword_id, keyword_name in zip(
            feature.keyword_ids,
            feature.keyword_names,
            strict=False,
        ):
            keyword_values[keyword_id].append(signal)
            keyword_names[keyword_id] = keyword_name
        for creator in feature.creators:
            creator_values[creator.casefold()].append(signal)

    return FeedbackTasteModel(
        genre_weights={key: _shrunk_affinity(values) for key, values in genre_values.items()},
        genre_names=genre_names,
        keyword_weights={key: _shrunk_affinity(values) for key, values in keyword_values.items()},
        keyword_names=keyword_names,
        creator_weights={key: _shrunk_affinity(values) for key, values in creator_values.items()},
        sample_size=len(usable),
    )


def feedback_match_score(
    model: FeedbackTasteModel | None,
    feature: MediaFeatureProfile,
) -> tuple[float, list[str]]:
    if model is None or model.sample_size == 0:
        return 0.0, []

    genre_values = [model.genre_weights[key] for key in feature.genre_ids if key in model.genre_weights]
    keyword_values = [
        model.keyword_weights[key] for key in feature.keyword_ids if key in model.keyword_weights
    ]
    creator_values = [
        model.creator_weights[name.casefold()]
        for name in feature.creators
        if name.casefold() in model.creator_weights
    ]

    genre_signal = sum(genre_values) / len(genre_values) if genre_values else 0.0
    keyword_signal = sum(keyword_values) / len(keyword_values) if keyword_values else 0.0
    creator_signal = max(creator_values, key=abs, default=0.0)
    score = genre_signal * 6.0 + keyword_signal * 4.0 + creator_signal * 3.0

    matches: list[tuple[float, str]] = []
    for genre_id, genre_name in zip(feature.genre_ids, feature.genre_names, strict=False):
        value = model.genre_weights.get(genre_id, 0.0)
        if value > 0.08:
            matches.append((value, genre_name))
    for keyword_id, keyword_name in zip(feature.keyword_ids, feature.keyword_names, strict=False):
        value = model.keyword_weights.get(keyword_id, 0.0)
        if value > 0.10:
            matches.append((value, keyword_name))
    for creator in feature.creators:
        value = model.creator_weights.get(creator.casefold(), 0.0)
        if value > 0.10:
            matches.append((value, creator))

    labels: list[str] = []
    for _value, label in sorted(matches, key=lambda item: (-item[0], item[1].casefold())):
        if label not in labels:
            labels.append(label)
        if len(labels) >= 2:
            break
    return max(-9.0, min(9.0, score)), labels


def _shrunk_affinity(values: list[float]) -> float:
    if not values:
        return 0.0
    raw = sum(values) / len(values)
    reliability = len(values) / (len(values) + 2.5)
    return max(-1.0, min(1.0, raw * reliability))
