import uuid
from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from ... import crud, schemas
from ...database import get_session
from ...models import User
from ...security import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("", response_model=List[schemas.NotificationResponse])
def get_my_notifications(
    unread_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Get notifications for the current user.
    """
    return crud.get_user_notifications(db, current_user.user_id, unread_only=unread_only)

@router.patch("/{notification_id}/read", status_code=status.HTTP_200_OK)
def mark_as_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Mark a specific notification as read.
    """
    success = crud.mark_notification_as_read(db, notification_id, current_user.user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"message": "Success"}

@router.patch("/read-all", status_code=status.HTTP_200_OK)
def mark_all_as_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Mark all unread notifications as read.
    """
    count = crud.mark_all_notifications_read(db, current_user.user_id)
    return {"message": f"Updated {count} notifications"}
