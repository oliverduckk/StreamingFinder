import pytest

from app.services.streaming_services import (
    get_service_for_provider_name,
    parse_requested_service_keys,
    validate_service_keys,
)


def test_parse_requested_service_keys_accepts_repeated_and_comma_separated_values() -> None:
    result = parse_requested_service_keys(["netflix,prime_video", "crunchyroll"])

    assert result == {"netflix", "prime_video", "crunchyroll"}


def test_prime_provider_variants_map_to_same_service() -> None:
    standard = get_service_for_provider_name("Amazon Prime Video")
    ads = get_service_for_provider_name("Amazon Prime Video with Ads")

    assert standard is not None
    assert ads is not None
    assert standard.key == "prime_video"
    assert ads.key == "prime_video"


def test_channel_addon_is_not_treated_as_direct_max_subscription() -> None:
    assert get_service_for_provider_name("HBO Max Amazon Channel") is None


def test_validate_service_keys_rejects_unknown_keys() -> None:
    with pytest.raises(ValueError, match="made_up_service"):
        validate_service_keys({"netflix", "made_up_service"})
