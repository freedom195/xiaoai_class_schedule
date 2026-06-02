from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional
from database import Child, get_session

router = APIRouter(prefix="/api/children", tags=["children"])


class ChildCreate(BaseModel):
    name: str
    avatar_emoji: str = "👦"


class ChildUpdate(BaseModel):
    name: Optional[str] = None
    avatar_emoji: Optional[str] = None


@router.get("")
def list_children(session: Session = Depends(get_session)):
    children = session.exec(select(Child).order_by(Child.total_xp.desc())).all()
    return children


@router.post("")
def create_child(body: ChildCreate, session: Session = Depends(get_session)):
    child = Child(name=body.name, avatar_emoji=body.avatar_emoji)
    session.add(child)
    session.commit()
    session.refresh(child)
    return child


@router.put("/{child_id}")
def update_child(child_id: int, body: ChildUpdate, session: Session = Depends(get_session)):
    child = session.get(Child, child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    if body.name is not None:
        child.name = body.name
    if body.avatar_emoji is not None:
        child.avatar_emoji = body.avatar_emoji
    session.add(child)
    session.commit()
    session.refresh(child)
    return child


@router.delete("/{child_id}")
def delete_child(child_id: int, session: Session = Depends(get_session)):
    child = session.get(Child, child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    session.delete(child)
    session.commit()
    return {"ok": True}
