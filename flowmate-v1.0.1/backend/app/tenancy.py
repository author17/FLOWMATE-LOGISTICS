"""Multi-business isolation.
Every business-owned table carries business_id. Once a request is authenticated, the database session is stamped with the
user's business (session.info["business_id"]); from then on EVERY query, update and delete on a business-owned table is
automatically limited to that business, and every new row is stamped with it. A user can therefore never read or change
another business's data, even by guessing ids."""
from sqlalchemy import Integer, event
from sqlalchemy.orm import Mapped, mapped_column, Session, with_loader_criteria

class Tenant:
    business_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

@event.listens_for(Session, "do_orm_execute")
def _limit_to_business(state):
    bid = state.session.info.get("business_id")
    if bid is None: return
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(with_loader_criteria(Tenant, lambda cls: cls.business_id == bid, include_aliases=True))

@event.listens_for(Session, "before_flush")
def _stamp_business(session, ctx, instances):
    bid = session.info.get("business_id")
    if bid is None: return
    for o in list(session.new) + list(session.dirty):
        if isinstance(o, Tenant):
            if o.business_id is None: o.business_id = bid
            elif o.business_id != bid: raise PermissionError("Cross-business write blocked")

_FKS: dict = {}
def _fk_list(table):
    if table not in _FKS: _FKS[table] = [(c.name, fk.column.table) for c in table.columns for fk in c.foreign_keys if "business_id" in fk.column.table.c]
    return _FKS[table]

@event.listens_for(Session, "before_flush")
def _check_references(session, ctx, instances):
    """Strict rule: a row may only point to rows of the SAME business (e.g. an order cannot use another business's product or location)."""
    bid = session.info.get("business_id")
    if bid is None: return
    from sqlalchemy import select
    seen = {}
    for o in list(session.new) + list(session.dirty):
        if not isinstance(o, Tenant): continue
        for col, ref in _fk_list(o.__table__):
            v = getattr(o, o.__mapper__.get_property_by_column(o.__table__.c[col]).key, None)
            if v is None: continue
            k = (ref.name, v)
            if k not in seen:
                r = session.connection().execute(select(ref.c.business_id).where(ref.c.id == v)).first()
                seen[k] = r is not None and r[0] == bid
            if not seen[k]: raise PermissionError(f"Cross-business reference blocked ({o.__table__.name}.{col})")

def use_business(db, business_id):
    """Run this session as one business (background jobs, public pages, webhooks)."""
    db.info["business_id"] = business_id; return db

# ---- per-business settings (the settings table keys are stored as "<business id>:<name>") ----
def _k(db, name): return f"{db.info.get('business_id') or 0}:{name}"

def get_setting(db, name, default=""):
    from . import models
    r = db.get(models.Setting, _k(db, name)); return r.value if r and r.value is not None else default

def put_setting(db, name, value):
    from . import models
    r = db.get(models.Setting, _k(db, name)) or models.Setting(key=_k(db, name)); r.value = str(value); db.add(r); return r

def all_settings(db) -> dict:
    from . import models
    from sqlalchemy import select
    pre = f"{db.info.get('business_id') or 0}:"
    return {r.key[len(pre):]: r.value for r in db.scalars(select(models.Setting)) if r.key.startswith(pre)}

def del_setting(db, name):
    from . import models
    r = db.get(models.Setting, _k(db, name))
    if r: db.delete(r)
