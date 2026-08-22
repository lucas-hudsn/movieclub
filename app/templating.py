from pathlib import Path

from fastapi.templating import Jinja2Templates

MONTH_NAMES = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def month_name(period: str) -> str:
    year, month = (int(p) for p in period.split("-"))
    return f"{MONTH_NAMES[month - 1]} {year}"


templates.env.filters["month"] = month_name
