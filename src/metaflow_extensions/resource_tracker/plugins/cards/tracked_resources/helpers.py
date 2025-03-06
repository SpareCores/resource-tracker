def pretty_number(num):
    """Format a number with comma big marks and keep up to 2 decimal places."""
    if num is None:
        return ""

    try:
        num = float(num)

        # integers or numbers that are effectively integers
        if num.is_integer():
            return f"{int(num):,}"

        # numbers with decimal places, limit to 2 decimal places
        formatted = f"{num:.2f}"
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
