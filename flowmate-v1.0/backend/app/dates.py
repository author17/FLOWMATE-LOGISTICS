"""Database-neutral day/range filters (comparing a DATE() result with text works on SQLite but not on Postgres)."""
from datetime import datetime, date, time, timedelta

def start(d: date) -> datetime: return datetime.combine(d, time.min)
def on_day(col, d: date): return (col >= start(d)) & (col < start(d + timedelta(days=1)))
def since(col, d: date): return col >= start(d)
def before(col, d: date): return col < start(d)
