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
