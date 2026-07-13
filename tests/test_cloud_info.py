import json
from io import BytesIO
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def clear_cloud_info_cache():
    from resource_tracker import cloud_info

    cloud_info.get_cloud_info.cache_clear()
    for check_fn in (
        cloud_info._check_aws,
        cloud_info._check_gcp,
        cloud_info._check_azure,
        cloud_info._check_hetzner,
        cloud_info._check_upcloud,
        cloud_info._check_alicloud,
        cloud_info._check_ovh,
        cloud_info._check_vultr,
    ):
        check_fn.cache_clear()
    yield


def test_check_vultr_parses_metadata():
    from resource_tracker.cloud_info import _check_vultr

    payload = {
        "hostname": "vultr-guest",
        "instanceid": "a747bfz6385e",
        "instance-v2-id": "36e9cf60-5d93-4e31-8ebf-613b3d2874fb",
        "region": {"regioncode": "EWR", "countrycode": "US"},
    }

    def fake_urlopen(request, timeout=0):
        url = request.full_url if hasattr(request, "full_url") else request
        assert url == "http://169.254.169.254/v1.json"
        return BytesIO(json.dumps(payload).encode("utf-8"))

    with patch("resource_tracker.cloud_info.urllib.request.urlopen", fake_urlopen):
        assert _check_vultr() == {
            "vendor": "vultr",
            "instance_type": "unknown",
            "region": "EWR",
        }


def test_check_vultr_rejects_non_vultr_json():
    from resource_tracker.cloud_info import _check_vultr

    def fake_urlopen(request, timeout=0):
        return BytesIO(json.dumps({"cloud_name": "upcloud"}).encode("utf-8"))

    with patch("resource_tracker.cloud_info.urllib.request.urlopen", fake_urlopen):
        assert _check_vultr() == {}
