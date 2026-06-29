from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional
from database import Child, ScheduleItem, Completion, PointsTransaction, RedemptionRequest, Badge, get_session
from event_logger import log_event

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
    log_event("CHILD", f"操作: 添加孩子 | 姓名: {child.name}")
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
    # Cascade: delete all related data
    items = session.exec(select(ScheduleItem).where(ScheduleItem.child_id == child_id)).all()
    item_ids = [i.id for i in items]
    for iid in item_ids:
        for c in session.exec(select(Completion).where(Completion.schedule_item_id == iid)).all():
            session.delete(c)
    for i in items:
        session.delete(i)
    for txn in session.exec(select(PointsTransaction).where(PointsTransaction.child_id == child_id)).all():
        session.delete(txn)
    for req in session.exec(select(RedemptionRequest).where(RedemptionRequest.child_id == child_id)).all():
        session.delete(req)
    for badge in session.exec(select(Badge).where(Badge.child_id == child_id)).all():
        session.delete(badge)
    name = child.name
    session.delete(child)
    session.commit()
    log_event("CHILD", f"操作: 删除孩子 | 姓名: {name}")
    return {"ok": True}
