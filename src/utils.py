
def render_currency(input):
    """$1,352.02 or -$94.59"""
    val = abs(input)
    sign = "-" if input < 0 else ""
    return f"{sign}${val:,.2f}"