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

def adopt_legacy():
    """Upgrade from the single-company versions: the existing data becomes Business #1; per-business unique keys on PostgreSQL.
    Runs the data adoption exactly once (only while there is no business yet)."""
    import re, secrets
    from sqlalchemy import select, func
    from .db import SessionLocal
    from . import models, config
    from .security import hash_password  # noqa
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(models.Business)) == 0 and db.scalar(select(func.count()).select_from(models.User)) > 0:
            name = db.scalar(select(models.Setting.value).where(models.Setting.key == "company_name")) or "My business"
            db.add(models.Business(id=1, name=name, slug="main", kind="general", inbound_token=config.INBOUND_EMAIL_TOKEN or secrets.token_urlsafe(24), terms_accepted_at=None)); db.flush()
            for s in db.scalars(select(models.Setting)):
                if not re.match(r"^\d+:", s.key): s.key = "1:" + s.key
            db.flush()
            for t in Base.metadata.sorted_tables:
                if "business_id" in t.c: db.execute(t.update().where(t.c.business_id.is_(None)).values(business_id=1))
            db.commit(); print("migrate: existing data adopted as business #1")
    if engine.dialect.name == "postgresql":
        with engine.begin() as cx:
            cx.execute(text("SELECT setval(pg_get_serial_sequence('businesses','id'), GREATEST((SELECT COALESCE(MAX(id),1) FROM businesses),1))"))
            insp = inspect(cx)
            for table, col, name in (("products", "sku", "uq_product_biz_sku"), ("categories", "name", "uq_category_biz_name")):
                for uc in insp.get_unique_constraints(table):
                    if uc["column_names"] == [col]: cx.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{uc["name"]}"'))
                for ix in insp.get_indexes(table):
                    if ix.get("unique") and ix["column_names"] == [col] and not ix["name"].startswith("uq_"): cx.execute(text(f'DROP INDEX IF EXISTS "{ix["name"]}"'))
                if name not in {u["name"] for u in insp.get_unique_constraints(table)}:
                    cx.execute(text(f'ALTER TABLE "{table}" ADD CONSTRAINT {name} UNIQUE (business_id, "{col}")'))
            for t in Base.metadata.sorted_tables:
                if "business_id" in t.c: cx.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{t.name}_business_id ON "{t.name}" (business_id)'))
