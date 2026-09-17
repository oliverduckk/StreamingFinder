from app.clients.tmdb import group_subscription_providers


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

    providers = group_subscription_providers(regional_results)

    prime = _provider_by_key(providers, "prime_video")
    netflix = _provider_by_key(providers, "netflix")

    assert prime.service_name == "Amazon Prime Video"
    assert prime.provider_ids == [9, 119, 2100]
    assert prime.countries == ["AU", "JP"]

    assert netflix.service_name == "Netflix"
    assert netflix.provider_ids == [8, 1796]
    assert netflix.countries == ["AU", "JP"]

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
    )

    assert len(providers) == 1
    assert providers[0].service_key == "max"
    assert providers[0].provider_ids == [1899]
