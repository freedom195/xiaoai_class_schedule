from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from database import (
    Child, Completion, PointsTransaction, RedemptionRequest,
    ScheduleItem, get_session,
)
from points_engine import settle_completion

router = APIRouter(prefix="/api", tags=["points"])


# ---------- completions ----------

class CompletionCreate(BaseModel):
    schedule_item_id: int
    child_id: int
    voice_raw: Optional[str] = None
    completion_date: Optional[str] = None   # YYYY-MM-DD, defaults to today


@router.post("/completions")
async def mark_complete(body: CompletionCreate, session: Session = Depends(get_session)):
    item = session.get(ScheduleItem, body.schedule_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Schedule item not found")

    result = await settle_completion(
        session, item, body.child_id, body.voice_raw, body.completion_date
    )
    if not result["ok"]:
        raise HTTPException(status_code=409, detail=result["error"])
    return result


@router.get("/completions")
def list_completions(
    child_id: Optional[int] = None,
    date: Optional[str] = None,
    session: Session = Depends(get_session),
):
    stmt = select(Completion)
    if child_id:
        stmt = stmt.where(Completion.child_id == child_id)
    if date:
        day = datetime.fromisoformat(date)
        stmt = stmt.where(
            Completion.completed_at >= day.replace(hour=0, minute=0, second=0),
            Completion.completed_at <= day.replace(hour=23, minute=59, second=59),
        )
    return session.exec(stmt.order_by(Completion.completed_at.desc())).all()


# ---------- points ----------

@router.get("/points/{child_id}")
def get_points(child_id: int, limit: int = 20, session: Session = Depends(get_session)):
    child = session.get(Child, child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    txns = session.exec(
        select(PointsTransaction)
        .where(PointsTransaction.child_id == child_id)
        .order_by(PointsTransaction.created_at.desc())
        .limit(limit)
    ).all()
    return {"child": child, "transactions": txns}


# ---------- redemptions ----------

class RedemptionCreate(BaseModel):
    child_id: int
    reward_name: str
    points_cost: int


class RedemptionReview(BaseModel):
    status: str   # approved / rejected
    parent_note: Optional[str] = None


@router.get("/redemptions")
def list_redemptions(
    status: Optional[str] = None,
    child_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    stmt = select(RedemptionRequest).order_by(RedemptionRequest.created_at.desc())
    if status:
        stmt = stmt.where(RedemptionRequest.status == status)
    if child_id:
        stmt = stmt.where(RedemptionRequest.child_id == child_id)
    return session.exec(stmt).all()


@router.post("/redemptions")
def create_redemption(body: RedemptionCreate, session: Session = Depends(get_session)):
    child = session.get(Child, body.child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    if child.available_points < body.points_cost:
        raise HTTPException(status_code=400, detail="Insufficient points")
    req = RedemptionRequest(
        child_id=body.child_id,
        reward_name=body.reward_name,
        points_cost=body.points_cost,
    )
    session.add(req)
    session.commit()
    session.refresh(req)
    return req


@router.put("/redemptions/{req_id}")
def review_redemption(req_id: int, body: RedemptionReview, session: Session = Depends(get_session)):
    req = session.get(RedemptionRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="Already reviewed")
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be approved or rejected")

    req.status = body.status
    req.parent_note = body.parent_note
    req.resolved_at = datetime.now()

    if body.status == "approved":
        child = session.get(Child, req.child_id)
        child.available_points -= req.points_cost
        session.add(child)
        txn = PointsTransaction(
            child_id=req.child_id,
            delta=-req.points_cost,
            reason=f"兑换：{req.reward_name}",
        )
        session.add(txn)

    session.add(req)
    session.commit()
    session.refresh(req)
    return req
