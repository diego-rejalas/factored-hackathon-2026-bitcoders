from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth import get_current_admin
from app.db import get_store

router = APIRouter(prefix="/admin/disputes", tags=["admin"])

# State machine, in code (not in any prompt): a human claims a case and closes it.
# 'auto_resolved' is only ever set by the system (POST /disputes/{id}/resolve), never here.
TRANSITIONS = {
    "claim": {"from": ("escalated", "open"), "to": "in_progress"},
    "close": {"from": ("in_progress",), "to": "closed"},
}

RESOLUTIONS = ("resolved_customer", "no_resolution")


class TransitionRequest(BaseModel):
    action: str = Field(pattern="^(claim|close)$")
    note: str = Field(min_length=1, max_length=2000)
    resolution: str | None = Field(
        default=None,
        description="Required when action=close: resolved_customer or no_resolution",
    )


@router.get("")
async def list_disputes(
    status_filter: str | None = Query(default=None, alias="status"),
    customer_id: str | None = Query(default=None, min_length=2),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: str = Depends(get_current_admin),
    store=Depends(get_store),
) -> dict:
    items = await store.admin_list_disputes(
        status_filter=status_filter, customer_id=customer_id, limit=limit, offset=offset
    )
    total = await store.admin_count_disputes(
        status_filter=status_filter, customer_id=customer_id
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{case_id}")
async def get_dispute(
    case_id: str,
    admin: str = Depends(get_current_admin),
    store=Depends(get_store),
) -> dict:
    dispute = await store.admin_get_dispute(case_id)
    if dispute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found")
    handoff = (dispute.get("evidence") or {}).get("handoff") or None
    dispute["events"] = await store.get_dispute_events(case_id)
    dispute["handoff"] = handoff
    dispute["conversation_id"] = (handoff or {}).get("conversation_id")
    return dispute


@router.post("/{case_id}/transition")
async def transition_dispute(
    case_id: str,
    body: TransitionRequest,
    admin: str = Depends(get_current_admin),
    store=Depends(get_store),
) -> dict:
    if not body.note.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A non-empty audit note is required")
    if body.action == "close" and body.resolution not in RESOLUTIONS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "close requires resolution in (resolved_customer, no_resolution)",
        )
    rule = TRANSITIONS[body.action]
    existing = await store.admin_get_dispute(case_id)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found")
    if existing["status"] not in rule["from"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot {body.action} a case in status '{existing['status']}'",
        )
    payload: dict = {"admin": admin, "note": body.note.strip()}
    if body.resolution:
        payload["resolution"] = body.resolution
    updated = await store.admin_transition(
        case_id, rule["to"], rule["from"], f"admin_{body.action}", payload
    )
    if updated is None:  # raced with another admin: re-check and reject
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Case changed state, reload and retry"
        )
    updated["events"] = await store.get_dispute_events(case_id)
    return updated
