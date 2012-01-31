import datetime, time, calendar

def feeddate(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

def now():
    """Timestamp for now (in UTC)"""
    return calendar.timegm(time.gmtime())

def today():
    """Ordinal for today (in UTC)"""
    return datetime.date.fromtimestamp(now())
