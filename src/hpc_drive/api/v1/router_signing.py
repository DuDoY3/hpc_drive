"""
Signing Workflow API Router

Provides endpoints for PDF signing workflow:
1. Create signing request (lecturer)
2. Submit request for approval (lecturer)
3. List my requests (lecturer)
4. List pending requests (admin)
5. Approve request (admin)
6. Reject request (admin)

Workflow:
DRAFT → PENDING → APPROVED/REJECTED

Permission model:
- LECTURER: Can create, submit, view own requests
- ADMIN: Can approve, reject, view all pending requests
"""

import logging
import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_session
from ...security import get_current_user, get_current_admin_user, oauth2_scheme
from ...models import User, DriveItem, SigningRequest, SigningStatus, ItemType
from ...schemas_signing import (
    SigningRequestCreate,
    SigningRequestUpdate,
    SigningRequestResponse
)
from ...integrations import system_management_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signing", tags=["Signing Workflow"])


# ===== Helper Functions =====

def get_signing_request_with_details(
    session: Session,
    request_id: uuid.UUID
) -> dict:
    """
    Get signing request with related data (file name, user names).
    """
    request = session.query(SigningRequest).filter(
        SigningRequest.request_id == request_id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Signing request not found")
    
    # Get drive item
    drive_item = session.query(DriveItem).filter(
        DriveItem.item_id == request.drive_item_id
    ).first()
    
    # Get requester
    requester = session.query(User).filter(
        User.user_id == request.requester_id
    ).first()
    
    # Get approver (if set)
    approver = None
    if request.approver_id:
        approver = session.query(User).filter(
            User.user_id == request.approver_id
        ).first()
    
    return {
        "request_id": request.request_id,
        "drive_item_id": request.drive_item_id,
        "requester_id": request.requester_id,
        "approver_id": request.approver_id,
        "current_status": request.current_status.value,
        "admin_comment": request.admin_comment,
        "signed_file_path": request.signed_file_path,
        "created_at": request.created_at,
        "updated_at": request.updated_at,
        "approved_at": request.approved_at,
        "file_name": drive_item.name if drive_item else None,
        "requester_name": requester.username if requester else None,
        "approver_name": approver.username if approver else None
    }


# ===== Endpoints =====

@router.post("/request", response_model=SigningRequestResponse)
async def create_signing_request(
    data: SigningRequestCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new signing request (DRAFT status).
    
    **Permission:** Lecturer only
    **Requirements:**
    - File must exist
    - File must be PDF
    - File must belong to requester
    """
    # Only lecturers can create signing requests
    if current_user.role.value not in ["TEACHER", "ADMIN"]:
        raise HTTPException(
            status_code=403,
            detail="Only lecturers can create signing requests"
        )
    
    # Check if file exists
    drive_item = session.query(DriveItem).filter(
        DriveItem.item_id == data.drive_item_id
    ).first()
    
    if not drive_item:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check if file belongs to user (unless admin)
    if current_user.role.value != "ADMIN" and drive_item.owner_id != current_user.user_id:
        raise HTTPException(
            status_code=403,
            detail="You can only request signing for your own files"
        )
    
    # Check if file is PDF
    if drive_item.item_type != ItemType.FILE:
        raise HTTPException(status_code=400, detail="Only files can be signed")
    
    if drive_item.file_metadata and not drive_item.name.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files can be signed")
    
    # Check if request already exists for this file
    existing = session.query(SigningRequest).filter(
        SigningRequest.drive_item_id == data.drive_item_id,
        SigningRequest.current_status.in_([SigningStatus.DRAFT, SigningStatus.PENDING])
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Signing request already exists for this file (status: {existing.current_status.value})"
        )
    
    # Create signing request
    signing_request = SigningRequest(
        request_id=uuid.uuid4(),
        drive_item_id=data.drive_item_id,
        requester_id=current_user.user_id,
        approver_id=data.approver_id,
        current_status=SigningStatus.DRAFT
    )
    
    session.add(signing_request)
    session.commit()
    session.refresh(signing_request)
    
    logger.info(f"Created signing request {signing_request.request_id} by user {current_user.user_id}")
    
    return SigningRequestResponse(**get_signing_request_with_details(session, signing_request.request_id))


@router.put("/{request_id}/submit", response_model=SigningRequestResponse)
async def submit_signing_request(
    request_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Submit signing request for approval (DRAFT → PENDING).
    
    **Permission:** Request owner only
    """
    request = session.query(SigningRequest).filter(
        SigningRequest.request_id == request_id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Signing request not found")
    
    # Check ownership
    if request.requester_id != current_user.user_id and current_user.role.value != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="You can only submit your own requests"
        )
    
    # Check status
    if request.current_status != SigningStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Can only submit DRAFT requests (current: {request.current_status.value})"
        )
    
    # Update status
    request.current_status = SigningStatus.PENDING
    session.commit()
    
    logger.info(f"Submitted signing request {request_id}")
    
    return SigningRequestResponse(**get_signing_request_with_details(session, request_id))


@router.get("/my-requests", response_model=List[SigningRequestResponse])
async def get_my_signing_requests(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get all signing requests created by current user.
    
    **Permission:** Lecturer
    """
    requests = session.query(SigningRequest).filter(
        SigningRequest.requester_id == current_user.user_id
    ).order_by(SigningRequest.created_at.desc()).all()
    
    result = []
    for req in requests:
        result.append(SigningRequestResponse(**get_signing_request_with_details(session, req.request_id)))
    
    return result


@router.get("/pending", response_model=List[SigningRequestResponse])
async def get_pending_signing_requests(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get all pending signing requests.
    
    **Permission:** Admin only
    """
    requests = session.query(SigningRequest).filter(
        SigningRequest.current_status == SigningStatus.PENDING
    ).order_by(SigningRequest.created_at.asc()).all()
    
    result = []
    for req in requests:
        result.append(SigningRequestResponse(**get_signing_request_with_details(session, req.request_id)))
    
    return result


@router.put("/{request_id}/approve", response_model=SigningRequestResponse)
async def approve_signing_request(
    request_id: uuid.UUID,
    update_data: SigningRequestUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
    token: str = Depends(oauth2_scheme)
):
    """
    Approve a signing request (PENDING → APPROVED).
    
    **Permission:** Admin only
    **Side effects:**
    - Sets approver_id, approved_at
    - Notifies requester
    """
    request = session.query(SigningRequest).filter(
        SigningRequest.request_id == request_id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Signing request not found")
    
    # Check status
    if request.current_status != SigningStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Can only approve PENDING requests (current: {request.current_status.value})"
        )
    
    # Update request
    request.current_status = SigningStatus.APPROVED
    request.approver_id = current_user.user_id
    request.approved_at = datetime.utcnow()
    request.admin_comment = update_data.admin_comment
    
    # TODO: Phase 2 - Generate signed PDF file
    # For now, just mark as approved
    
    session.commit()
    
    logger.info(f"Approved signing request {request_id} by admin {current_user.user_id}")
    
    # Notify requester (don't fail if notification fails)
    try:
        await system_management_service.send_notification(
            token=token,
            user_id=request.requester_id,
            title="Signing Request Approved",
            message=f"Your signing request has been approved by {current_user.username}",
            type="SIGNING_APPROVED",
            priority="HIGH",
            metadata={
                "request_id": str(request_id),
                "admin_comment": update_data.admin_comment or ""
            }
        )
        logger.info(f"Notification sent for approved request {request_id}")
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
    
    return SigningRequestResponse(**get_signing_request_with_details(session, request_id))


@router.put("/{request_id}/reject", response_model=SigningRequestResponse)
async def reject_signing_request(
    request_id: uuid.UUID,
    update_data: SigningRequestUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
    token: str = Depends(oauth2_scheme)
):
    """
    Reject a signing request (PENDING → REJECTED).
    
    **Permission:** Admin only
    **Side effects:** Notifies requester
    """
    request = session.query(SigningRequest).filter(
        SigningRequest.request_id == request_id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Signing request not found")
    
    # Check status
    if request.current_status != SigningStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Can only reject PENDING requests (current: {request.current_status.value})"
        )
    
    # Update request
    request.current_status = SigningStatus.REJECTED
    request.approver_id = current_user.user_id
    request.admin_comment = update_data.admin_comment
    
    session.commit()
    
    logger.info(f"Rejected signing request {request_id} by admin {current_user.user_id}")
    
    # Notify requester
    try:
        await system_management_service.send_notification(
            token=token,
            user_id=request.requester_id,
            title="Signing Request Rejected",
            message=f"Your signing request was rejected by {current_user.username}. Reason: {update_data.admin_comment or 'No reason provided'}",
            type="SIGNING_REJECTED",
            priority="HIGH",
            metadata={
                "request_id": str(request_id),
                "admin_comment": update_data.admin_comment or ""
            }
        )
        logger.info(f"Notification sent for rejected request {request_id}")
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
    
    return SigningRequestResponse(**get_signing_request_with_details(session, request_id))