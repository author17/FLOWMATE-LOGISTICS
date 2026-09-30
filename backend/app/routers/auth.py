from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import verify_password, make_token, current_user, require, hash_password
from .. import models, audit

router = APIRouter(prefix="/api", tags=["auth"])

@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.scalar(select(models.User).where(models.User.email == form.username))
    if not u or not u.active or not verify_password(form.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password")
    audit.log(db, u, "login", "user", u.id); db.commit()
    return {"access_token": make_token(u), "token_type": "bearer", "user": {"id": u.id, "name": u.name, "role": u.role}}

@router.get("/auth/me")
def me(u=Depends(current_user)): return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "location_id": u.location_id}

class NewUser(BaseModel):
    name: str; email: str; password: str; role: str = "employee"; location_id: int | None = None

@router.get("/users")
def users(db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    return [{"id": x.id, "name": x.name, "email": x.email, "role": x.role, "location_id": x.location_id, "active": x.active} for x in db.scalars(select(models.User))]

@router.post("/users", status_code=201)
def add_user(d: NewUser, db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    if len(d.password) < 8: raise HTTPException(422, "Password must be at least 8 characters")
    n = models.User(name=d.name, email=d.email, password_hash=hash_password(d.password), role=d.role, location_id=d.location_id)
    db.add(n); db.flush(); audit.log(db, u, "create_user", "user", n.id, None, {"email": d.email, "role": d.role}); db.commit()
    return {"id": n.id}
