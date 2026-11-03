"""Jinja2 formatting and helper filters."""

def format_paise(paise: int) -> str:
    """Format integer paise as Indian Rupee string (e.g. 735000 -> '₹7,350')."""
    if paise is None:
        return "₹0"
    rupees = paise // 100
    # Indian numbering formatting (e.g. 1,00,000)
    s = str(abs(rupees))
    if len(s) <= 3:
        formatted = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        groups.reverse()
        formatted = ",".join(groups) + "," + last3
    prefix = "-" if paise < 0 else ""
    return f"{prefix}₹{formatted}"


def format_date_str(d) -> str:
    """Format date to human readable e.g. '14 Nov 2026'."""
    if not d:
        return ""
    return d.strftime("%d %b %Y")


def format_date_short(d) -> str:
    """Format date short e.g. '14 Nov'."""
    if not d:
        return ""
    return d.strftime("%d %b")

