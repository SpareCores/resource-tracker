"""
This module attempts to determine if the code is running on a cloud server,
and returns standardized information about the cloud provider and instance.
"""

import json
import urllib.error
import urllib.request
from contextlib import suppress
from functools import cache
from typing import Dict

METADATA_REQUEST_TIMEOUT = 2


@cache
def get_cloud_info() -> Dict[str, str]:
    """
    Detect cloud environment and return standardized information.

    Returns:
        Dict[str, str]: A dictionary containing standardized cloud information:
            - vendor: The cloud provider (aws, gcp, azure, hcloud, upcloud) or None
            - instance_type: The instance type/size/flavor
            - region: The region/zone where the instance is running
    """
    for check_fn in [
        _check_aws,
        _check_gcp,
        _check_azure,
        _check_hetzner,
        _check_upcloud,
    ]:
        info = check_fn()
        if info:
            return info

    return {"vendor": "unknown", "instance_type": "unknown", "region": "unknown"}


@cache
def _check_aws() -> Dict[str, str]:
    """Check if running on AWS and return standardized info.

    References: <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-metadata.html>"""

    with suppress(Exception):
        # Get token for IMDSv2
        token_request = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
            method="PUT",
        )
        with urllib.request.urlopen(
            token_request, timeout=METADATA_REQUEST_TIMEOUT
        ) as response:
            token = response.read().decode("utf-8")

        headers = {"X-aws-ec2-metadata-token": token}

        instance_type = "unknown"
        with suppress(Exception):
            request = urllib.request.Request(
                "http://169.254.169.254/latest/meta-data/instance-type", headers=headers
            )
            with urllib.request.urlopen(
                request, timeout=METADATA_REQUEST_TIMEOUT
            ) as response:
                instance_type = response.read().decode("utf-8")

        region = "unknown"
        with suppress(Exception):
            request = urllib.request.Request(
                "http://169.254.169.254/latest/meta-data/placement/region",
                headers=headers,
            )
            with urllib.request.urlopen(
                request, timeout=METADATA_REQUEST_TIMEOUT
            ) as response:
                region = response.read().decode("utf-8")

        return {"vendor": "aws", "instance_type": instance_type, "region": region}
    return {}


@cache
def _check_gcp() -> Dict[str, str]:
    """Check if running on Google Cloud Platform and return standardized info.

    References: <https://cloud.google.com/compute/docs/metadata/overview>"""

    with suppress(Exception):
        headers = {"Metadata-Flavor": "Google"}

        request = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/instance/machine-type",
            headers=headers,
        )
        with urllib.request.urlopen(
            request, timeout=METADATA_REQUEST_TIMEOUT
        ) as response:
            machine_type = response.read().decode("utf-8")
            # projects/PROJECT_NUM/machineTypes/MACHINE_TYPE
            instance_type = machine_type.split("/")[-1]

        request = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/instance/zone",
            headers=headers,
        )
        with urllib.request.urlopen(
            request, timeout=METADATA_REQUEST_TIMEOUT
        ) as response:
            zone_text = response.read().decode("utf-8")
            # projects/PROJECT_NUM/zones/ZONE
            zone = zone_text.split("/")[-1]
            # region is the zone without the last part (e.g., us-central1-a -> us-central1)
            region = "-".join(zone.split("-")[:-1]) if "-" in zone else zone

        return {"vendor": "gcp", "instance_type": instance_type, "region": region}
    return {}


@cache
def _check_azure() -> Dict[str, str]:
    """Check if running on Microsoft Azure and return standardized info.

    References: <https://learn.microsoft.com/en-us/azure/virtual-machines/instance-metadata-service>"""
    with suppress(Exception):
        request = urllib.request.Request(
            "http://169.254.169.254/metadata/instance?api-version=2021-02-01",
            headers={"Metadata": "true"},
        )
        with urllib.request.urlopen(
            request, timeout=METADATA_REQUEST_TIMEOUT
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
            if "compute" in data:
                compute = data["compute"]
                return {
                    "vendor": "azure",
                    "instance_type": compute.get("vmSize", "unknown"),
                    "region": compute.get("location", "unknown"),
                }
    return {}


@cache
def _check_hetzner() -> Dict[str, str]:
    """Check if running on Hetzner Cloud and return standardized info.

    References: <https://docs.hetzner.cloud/#server-metadata>"""
    with suppress(Exception):
        with urllib.request.urlopen(
            "http://169.254.169.254/hetzner/v1/metadata",
            timeout=METADATA_REQUEST_TIMEOUT,
        ) as response:
            text = response.read().decode("utf-8")

            instance_type = "unknown"
            region = "unknown"
            with suppress(Exception):
                lines = text.strip().split("\n")
                for line in lines:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip()
                        value = value.strip()

                        if key == "instance-id":
                            instance_type = value
                        elif key == "region":
                            region = value
            return {
                "vendor": "hcloud",
                "instance_type": instance_type,
                "region": region,
            }
    return {}


@cache
def _check_upcloud() -> Dict[str, str]:
    """Check if running on UpCloud and return standardized info.

    References: <https://upcloud.com/docs/products/cloud-servers/features/metadata-service/>"""
    with suppress(Exception):
        with urllib.request.urlopen(
            "http://169.254.169.254/metadata/v1.json", timeout=METADATA_REQUEST_TIMEOUT
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("cloud_name") == "upcloud":
                return {
                    "vendor": "upcloud",
                    # no instance type in metadata
                    "instance_type": "unknown",
                    "region": data.get("region", "unknown"),
                }
    return {}
