"""Tiny safe auto-migration: adds any NEW columns that the models have but the existing database lacks, so upgrades never need a reset.
Only adds nullable columns (never drops or changes anything)."""
from sqlalchemy import inspect, text
from .db import engine, Base

def migrate():
    insp = inspect(engine)
    with engine.begin() as cx:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name): continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have: continue
                typ = col.type.compile(dialect=engine.dialect)
                default = " DEFAULT false" if typ.upper().startswith("BOOL") else ""
                cx.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {typ}{default}'))
                print(f"migrate: added {table.name}.{col.name}")
