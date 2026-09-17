from app.clients.tmdb import (
    build_country_name_map,
    extract_title_and_year,
    group_subscription_providers,
)


def _provider_by_key(providers, key: str):
    return next(provider for provider in providers if provider.service_key == key)


def test_group_subscription_providers_normalises_duplicate_service_variants() -> None:
    regional_results = {
        "AU": {
            "flatrate": [
                {
                    "provider_id": 119,
                    "provider_name": "Amazon Prime Video",
                    "logo_path": "/prime.png",
                },
                {
                    "provider_id": 2100,
                    "provider_name": "Amazon Prime Video with Ads",
                    "logo_path": "/prime-ads.png",
                },
                {
                    "provider_id": 8,
                    "provider_name": "Netflix",
                    "logo_path": "/netflix.png",
                },
            ],
            "rent": [
                {
                    "provider_id": 2,
                    "provider_name": "Apple TV Store",
                    "logo_path": "/apple-store.png",
                }
            ],
        },
        "JP": {
            "flatrate": [
                {
                    "provider_id": 9,
                    "provider_name": "Amazon Prime Video",
                    "logo_path": "/prime.png",
                },
                {
                    "provider_id": 1796,
                    "provider_name": "Netflix Standard with Ads",
                    "logo_path": "/netflix-ads.png",
                },
            ]
        },
    }

    providers = group_subscription_providers(
        regional_results,
        country_names={"AU": "Australia", "JP": "Japan"},
    )

    prime = _provider_by_key(providers, "prime_video")
    netflix = _provider_by_key(providers, "netflix")

    assert prime.service_name == "Amazon Prime Video"
    assert prime.provider_ids == [9, 119, 2100]
    assert [(country.code, country.name) for country in prime.countries] == [
        ("AU", "Australia"),
        ("JP", "Japan"),
    ]

    assert netflix.service_name == "Netflix"
    assert netflix.provider_ids == [8, 1796]
    assert [(country.code, country.name) for country in netflix.countries] == [
        ("AU", "Australia"),
        ("JP", "Japan"),
    ]

    assert all("Apple TV Store" != provider.service_name for provider in providers)


def test_group_subscription_providers_can_filter_to_selected_services() -> None:
    regional_results = {
        "AU": {
            "flatrate": [
                {
                    "provider_id": 8,
                    "provider_name": "Netflix",
                    "logo_path": "/netflix.png",
                },
                {
                    "provider_id": 119,
                    "provider_name": "Amazon Prime Video",
                    "logo_path": "/prime.png",
                },
                {
                    "provider_id": 1825,
                    "provider_name": "HBO Max Amazon Channel",
                    "logo_path": "/max-channel.png",
                },
            ]
        }
    }

    providers = group_subscription_providers(
        regional_results,
        service_keys={"netflix"},
        country_names={"AU": "Australia"},
    )

    assert [provider.service_key for provider in providers] == ["netflix"]


def test_direct_service_filter_does_not_include_channel_addons() -> None:
    regional_results = {
        "AU": {
            "flatrate": [
                {
                    "provider_id": 1899,
                    "provider_name": "HBO Max",
                    "logo_path": "/max.png",
                },
                {
                    "provider_id": 1825,
                    "provider_name": "HBO Max Amazon Channel",
                    "logo_path": "/max-channel.png",
                },
            ]
        }
    }

    providers = group_subscription_providers(
        regional_results,
        service_keys={"max"},
        country_names={"AU": "Australia"},
    )

    assert len(providers) == 1
    assert providers[0].service_key == "max"
    assert providers[0].provider_ids == [1899]


def test_country_name_map_prefers_english_name() -> None:
    mapping = build_country_name_map(
        [
            {
                "iso_3166_1": "JP",
                "english_name": "Japan",
                "native_name": "日本",
            },
            {
                "iso_3166_1": "AU",
                "english_name": "Australia",
                "native_name": "Australia",
            },
        ]
    )

    assert mapping == {"JP": "Japan", "AU": "Australia"}


def test_unknown_country_code_falls_back_to_code() -> None:
    providers = group_subscription_providers(
        {
            "ZZ": {
                "flatrate": [
                    {
                        "provider_id": 8,
                        "provider_name": "Netflix",
                        "logo_path": "/netflix.png",
                    }
                ]
            }
        },
        country_names={},
    )

    assert providers[0].countries[0].code == "ZZ"
    assert providers[0].countries[0].name == "ZZ"


def test_extract_movie_title_and_year() -> None:
    title, year = extract_title_and_year(
        "movie",
        {"title": "Interstellar", "release_date": "2014-11-05"},
    )

    assert title == "Interstellar"
    assert year == 2014


def test_extract_tv_title_and_year() -> None:
    title, year = extract_title_and_year(
        "tv",
        {"name": "Severance", "first_air_date": "2022-02-17"},
    )

    assert title == "Severance"
    assert year == 2022
