"""Registration request API endpoints for the admin panel."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, require_admin
from db.database import get_session
from db.enums import (
    RegistrationRequestStatus,
    REGISTRATION_REQUEST_STATUS_LABELS,
    UserRole,
    Language,
)
from db.models import RegistrationRequest, User, BusinessUnit

router = APIRouter()


USER_ROLE_LABELS = {
    "ADMIN": "Администратор",
    "RESORT_MANAGER": "Менеджер курорта",
    "RESTAURANT_MANAGER": "Менеджер ресторана",
    "OPERATOR": "Оператор",
}


class RequestDecision(BaseModel):
    status: str  # "APPROVED" or "REJECTED"
    role: Optional[str] = None  # Required if approved


# ── List all registration requests ──


@router.get("/list")
async def list_requests(
    status: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all registration requests, optionally filtered by status."""
    query = select(RegistrationRequest).order_by(RegistrationRequest.created_at.desc())

    if status:
        try:
            query = query.where(
                RegistrationRequest.status == RegistrationRequestStatus(status)
            )
        except ValueError:
            pass

    result = await session.execute(query)
    requests = result.scalars().all()

    items = []
    for r in requests:
        items.append({
            "id": r.id,
            "telegram_id": r.telegram_id,
            "full_name": r.full_name,
            "username": r.username,
            "status": r.status.value,
            "status_label": REGISTRATION_REQUEST_STATUS_LABELS.get(r.status, r.status.value),
            "assigned_role": r.assigned_role.value if r.assigned_role else None,
            "assigned_role_label": USER_ROLE_LABELS.get(r.assigned_role.value) if r.assigned_role else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        })

    # Count pending
    count_result = await session.execute(
        select(func.count(RegistrationRequest.id)).where(
            RegistrationRequest.status == RegistrationRequestStatus.PENDING
        )
    )
    pending_count = count_result.scalar()

    return {"requests": items, "pending_count": pending_count}


# ── Approve or reject a request ──


@router.put("/decide/{request_id}")
async def decide_request(
    request_id: int,
    decision: RequestDecision,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Approve or reject a registration request. Admin/Owner only."""
    require_admin(user)

    req = await session.get(RegistrationRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status != RegistrationRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Request already processed")

    if decision.status == "APPROVED":
        if not decision.role:
            raise HTTPException(status_code=400, detail="Role is required for approval")

        try:
            role = UserRole(decision.role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {decision.role}")

        # Create user
        existing_user = await session.execute(
            select(User).where(User.telegram_id == req.telegram_id)
        )
        if existing_user.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="User already exists")

        new_user = User(
            telegram_id=req.telegram_id,
            full_name=req.full_name,
            role=role,
            language=Language.RU,
            active_section=BusinessUnit.RESORT,
        )
        session.add(new_user)

        req.status = RegistrationRequestStatus.APPROVED
        req.assigned_role = role
        req.reviewed_by = user.get("telegram_id")
        req.reviewed_at = datetime.utcnow()

        await session.commit()

        return {
            "success": True,
            "message": f"Пользователь {req.full_name} добавлен с ролью {USER_ROLE_LABELS.get(role.value, role.value)}",
        }

    elif decision.status == "REJECTED":
        req.status = RegistrationRequestStatus.REJECTED
        req.reviewed_by = user.get("telegram_id")
        req.reviewed_at = datetime.utcnow()
        await session.commit()

        return {"success": True, "message": f"Заявка от {req.full_name} отклонена"}

    else:
        raise HTTPException(status_code=400, detail="Invalid status. Use APPROVED or REJECTED")


# ── Available roles for the dropdown ──


@router.get("/roles")
async def list_roles(user: dict = Depends(get_current_user)):
    """List available roles for assignment."""
    return {
        "roles": [
            {"value": r.value, "label": USER_ROLE_LABELS.get(r.value, r.value)}
            for r in UserRole
        ]
    }
