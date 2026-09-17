from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StreamingServiceDefinition:
    key: str
    name: str
    provider_names: frozenset[str]


# Stable application-level service keys.
#
# TMDB can expose multiple provider records for the same consumer-facing
# subscription. The desktop app, database and Mairon integration should use
# these stable keys instead of depending on TMDB provider IDs.
STREAMING_SERVICES: tuple[StreamingServiceDefinition, ...] = (
    StreamingServiceDefinition(
        key="netflix",
        name="Netflix",
        provider_names=frozenset({
            "Netflix",
            "Netflix Standard with Ads",
        }),
    ),
    StreamingServiceDefinition(
        key="prime_video",
        name="Amazon Prime Video",
        provider_names=frozenset({
            "Amazon Prime Video",
            "Amazon Prime Video with Ads",
        }),
    ),
    StreamingServiceDefinition(
        key="disney_plus",
        name="Disney+",
        provider_names=frozenset({
            "Disney Plus",
        }),
    ),
    StreamingServiceDefinition(
        key="crunchyroll",
        name="Crunchyroll",
        provider_names=frozenset({
            "Crunchyroll",
        }),
    ),
    StreamingServiceDefinition(
        key="apple_tv_plus",
        name="Apple TV+",
        provider_names=frozenset({
            "Apple TV+",
        }),
    ),
    StreamingServiceDefinition(
        key="max",
        name="HBO Max",
        provider_names=frozenset({
            "HBO Max",
        }),
    ),
    StreamingServiceDefinition(
        key="paramount_plus",
        name="Paramount+",
        provider_names=frozenset({
            "Paramount Plus",
            "Paramount Plus Basic with Ads",
            "Paramount Plus Essential",
            "Paramount Plus Premium",
        }),
    ),
    StreamingServiceDefinition(
        key="stan",
        name="Stan",
        provider_names=frozenset({
            "Stan",
        }),
    ),
)


def _normalise_provider_name(value: str) -> str:
    return " ".join(value.split()).casefold()


_SERVICE_BY_PROVIDER_NAME = {
    _normalise_provider_name(provider_name): service
    for service in STREAMING_SERVICES
    for provider_name in service.provider_names
}
_SERVICE_BY_KEY = {service.key: service for service in STREAMING_SERVICES}


def get_service_for_provider_name(
    provider_name: str,
) -> StreamingServiceDefinition | None:
    """Return the canonical service represented by a TMDB provider name."""
    return _SERVICE_BY_PROVIDER_NAME.get(_normalise_provider_name(provider_name))


def get_streaming_service(service_key: str) -> StreamingServiceDefinition | None:
    """Return a known service by stable application key."""
    return _SERVICE_BY_KEY.get(service_key.strip().casefold())


def parse_requested_service_keys(values: list[str] | None) -> set[str] | None:
    """Parse repeated or comma-separated service query parameters.

    Examples accepted by the API:
      ?services=netflix&services=prime_video
      ?services=netflix,prime_video
    """
    if not values:
        return None

    requested: set[str] = set()
    for value in values:
        for part in value.split(","):
            key = part.strip().casefold()
            if key:
                requested.add(key)

    return requested or None


def validate_service_keys(service_keys: set[str] | None) -> set[str] | None:
    """Validate service keys and return them unchanged when valid."""
    if service_keys is None:
        return None

    unknown = sorted(service_keys - _SERVICE_BY_KEY.keys())
    if unknown:
        raise ValueError(f"Unknown streaming service key(s): {', '.join(unknown)}")

    return service_keys
