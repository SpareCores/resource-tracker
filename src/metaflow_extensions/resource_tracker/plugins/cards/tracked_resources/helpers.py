from json import loads
from typing import Optional
from urllib.parse import urlencode
from urllib.request import urlopen


def pretty_number(num: float | int | None, digits: int = 2) -> str:
    """Format a number for HTML display.

    Non-numeric values are returned as a string.
    Integers are returned as-is.
    Numbers with decimal places are rounded to the specified number of digits and trailing zeros are removed.
    Big marks for thousands are added.

    Args:
        num: The number to format.
        digits: The number of decimal places to display.

    Returns:
        A string representation of the number.
    """
    try:
        num = float(num)

        # integers or numbers that are effectively integers
        if num.is_integer():
            return f"{int(num):,}"

        # numbers with decimal places, limit to the specified number of digits
        formatted = f"{num:.{digits}f}"
        # drop trailing zeros after decimal point
        if "." in formatted:
            formatted = (
                formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
            )

        # add big marks for thousands
        parts = formatted.split(".")
        parts[0] = f"{int(parts[0]):,}"
        return ".".join(parts)
    except (ValueError, TypeError):
        return str(num)


def round_memory(mb: float | int) -> int:
    """Round a number to the nearest meaningful memory amount.

    Args:
        mb: The number of MB to round.

    Returns:
        The rounded number of MB.

    Example:
        >>> round_memory(68)
        128
        >>> round_memory(896)
        1024
        >>> round_memory(3863)
        4096
    """
    if mb <= 128:
        rounded = 128
    elif mb <= 256:
        rounded = 256
    elif mb <= 512:
        rounded = 512
    elif mb <= 1024:
        rounded = 1024
    elif mb <= 2048:
        rounded = 2048
    else:
        # round up to the next GB
        rounded_gb = mb / 1024
        rounded = int(1024 * (rounded_gb // 1 + (1 if rounded_gb % 1 > 0 else 0)))
    return rounded


def get_instance_price(vendor_id, region_id, instance_type) -> float | None:
    """Get the on-demand price for a specific instance type in a region.

    Args:
        vendor_id: The ID of the vendor (e.g. "aws", "azure", "gcp")
        region_id: The ID of the region (e.g. "us-east-1", "us-west-2")
        instance_type: The type of instance (e.g. "t3.micro", "m5.large")

    Returns:
        The on-demand price for the instance type in the region, or None if no price is found.
    """
    try:
        url = f"https://keeper.sparecores.net/server/{vendor_id}/{instance_type}/prices"
        with urlopen(url, timeout=2) as response:
            pricing_data = loads(response.read().decode("utf-8"))

        for item in pricing_data:
            if (
                item.get("region_id") == region_id
                and item.get("allocation") == "ondemand"
                and item.get("operating_system") == "Linux"
            ):
                return item.get("price")

        # fallback to the first on-demand price in other regions
        for item in pricing_data:
            if (
                item.get("allocation") == "ondemand"
                and item.get("operating_system") == "Linux"
            ):
                return item.get("price")

        return None
    except Exception:
        return None


def get_recommended_cloud_servers(
    cpu: int,
    memory: int,
    gpu: Optional[int] = None,
    vram: Optional[int] = None,
    n: int = 10,
) -> list[dict]:
    """Get the cheapest cloud servers for the given resources from Spare Cores.

    Args:
        cpu: The minimum number of vCPUs.
        memory: The minimum amount of memory in MB.
        gpu: The minimum number of GPUs.
        vram: The minimum amount of VRAM in GB.
        n: The number of recommended servers to return.

    Returns:
        A list of recommended server configurations ordered by price.

    References:
        - https://sparecores.com/servers
    """
    try:
        params = {
            "vcpus_min": cpu,
            "memory_min": round(memory / 1024),  # convert MiB to GiB
            "order_by": "min_price_ondemand",
            "order_dir": "asc",
            "limit": n,
        }
        if gpu and gpu > 0:
            params["gpu_min"] = gpu
        if vram and vram > 0:
            params["gpu_memory_total"] = vram
        base_url = "https://keeper.sparecores.net/servers"
        url = f"{base_url}?{urlencode(params)}"
        with urlopen(url, timeout=5) as response:
            servers_data = loads(response.read().decode("utf-8"))
        return servers_data
    except Exception:
        return []
