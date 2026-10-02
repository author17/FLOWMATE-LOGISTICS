from sqlalchemy.orm import Session
from . import models

def log(db: Session, user, action: str, obj_type: str, obj_id="", old=None, new=None):
    db.add(models.AuditLog(user_id=getattr(user, "id", None), user_name=getattr(user, "name", "system"),
                           action=action, object_type=obj_type, object_id=str(obj_id), old_value=old, new_value=new))

def notify(db: Session, kind: str, message: str):
    db.add(models.Notification(kind=kind, message=message))
