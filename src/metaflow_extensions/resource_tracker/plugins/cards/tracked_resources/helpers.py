from json import loads
from urllib.request import urlopen


def pretty_number(num, digits=2):
    """Format a number with comma as big marks and keep up to 2 decimal places."""
    if num is None:
        return ""

    try:
        num = float(num)

        # integers or numbers that are effectively integers
        if num.is_integer():
            return f"{int(num):,}"

        # numbers with decimal places, limit to 2 decimal places
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


def round_memory(mb):
    """Round a number to the nearest meaningful memory amount.

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
