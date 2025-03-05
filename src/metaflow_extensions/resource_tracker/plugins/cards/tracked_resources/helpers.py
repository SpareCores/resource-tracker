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


def round_memory(num):
    """Round a number to the nearest meaningful memory amount."""
    if num <= 128:
        rec_mem = 128
    elif num <= 256:
        rec_mem = 256
    elif num <= 512:
        rec_mem = 512
    elif num <= 1024:
        rec_mem = 1024
    elif num <= 2048:
        rec_mem = 2048
    else:
        # round up to the next GB
        rec_mem_gb = num / 1024
        rec_mem = int(1024 * (rec_mem_gb // 1 + (1 if rec_mem_gb % 1 > 0 else 0)))
    return rec_mem
