"""Housing observation windows use the property's NYC calendar, regardless of server TZ."""
from datetime import datetime
from zoneinfo import ZoneInfo

NYC = ZoneInfo('America/New_York')


def nyc_today():
    return datetime.now(NYC).date()
