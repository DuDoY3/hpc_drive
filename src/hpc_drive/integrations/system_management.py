"""
System-Management API Integration Service

This service provides integration with the System-Management microservice
for the following functionality:
- Courses API: Get course lists for class storage auto-generation
- Departments API: Get department/unit lists
- Class Lecturers API: Permission checks (lecturer teaches class?)
- Class Students API: Get student lists for notifications
- Notification API: Send bulk notifications to users
"""

import os
import httpx
import logging
from typing import List, Dict, Any, Optional
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class SystemManagementService:
    """
    Service for integrating with System-Management API.
    
    Handles all external API calls to System-Management including:
    - Course management
    - Department/unit management
    - User/class relationships
    - Notification delivery
    """
    
    def __init__(self, base_url: str, timeout: float = 3.0):
        """
        Initialize the System-Management service.
        
        Args:
            base_url: Base URL of System-Management API (e.g., http://localhost:8000)
            timeout: Request timeout in seconds (default: 10)
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        logger.info(f"SystemManagementService initialized with base_url={self.base_url}")
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        token: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Internal helper to make HTTP requests to System-Management API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., /api/v1/courses)
            token: JWT token for authentication
            params: Query parameters
            json_data: JSON request body
            
        Returns:
            JSON response as dict
            
        Raises:
            HTTPException: If request fails
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.debug(f"Making {method} request to {url}")
                
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data
                )
                
                response.raise_for_status()
                result = response.json()
                
                logger.debug(f"Request successful: {method} {url}")
                return result
                
        except httpx.HTTPStatusError as e:
            logger.error(f"System-Management API HTTP error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"System-Management API error: {e.response.text}"
            )
        except httpx.TimeoutException:
            logger.error(f"System-Management API timeout: {url}")
            raise HTTPException(
                status_code=504,
                detail="System-Management API timeout"
            )
        except Exception as e:
            logger.error(f"System-Management API error: {str(e)}")
            raise HTTPException(
                status_code=502,
                detail=f"System-Management API error: {str(e)}"
            )
    
    # ===== 1. Courses API =====
    
    async def get_courses(
        self,
        token: str,
        semester_id: Optional[int] = None,
        lecturer_id: Optional[int] = None,
        department_id: Optional[int] = None,
        search: Optional[str] = None,
        per_page: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get list of courses from System-Management.
        
        Endpoint: GET /api/v1/attendance/courses
        
        Args:
            token: JWT authentication token
            semester_id: Filter by semester
            lecturer_id: Filter by lecturer
            department_id: Filter by department
            search: Search query
            per_page: Results per page (default: 100)
            
        Returns:
            List of course dictionaries with keys: id, name, code, semester_id, etc.
            
        Example:
            courses = await service.get_courses(token, semester_id=1, lecturer_id=2)
            # [{"id": 1, "name": "Lập trình Python", "code": "IT101", ...}]
        """
        params: Dict[str, Any] = {"per_page": per_page}
        
        if semester_id is not None:
            params["semester_id"] = semester_id
        if lecturer_id is not None:
            params["lecturer_id"] = lecturer_id
        if department_id is not None:
            params["department_id"] = department_id
        if search:
            params["search"] = search
        
        response = await self._make_request(
            "GET",
            "/api/v1/attendance/courses",
            token,
            params=params
        )
        
        return response.get("data", [])
    
    # ===== 2. Departments API =====
    
    async def get_departments(
        self,
        token: str
    ) -> List[Dict[str, Any]]:
        """
        Get list of all departments/units.
        
        Endpoint: GET /api/v1/departments
        
        Args:
            token: JWT authentication token
            
        Returns:
            List of department dictionaries with keys: id, name, code, units, etc.
            
        Example:
            departments = await service.get_departments(token)
            # [{"id": 3, "name": "Khoa CNTT", "units": [...]}]
        """
        response = await self._make_request(
            "GET",
            "/api/v1/departments",
            token
        )
        
        return response.get("data", [])
    
    async def get_department(
        self,
        token: str,
        department_id: int
    ) -> Dict[str, Any]:
        """
        Get a specific department by ID.
        
        Args:
            token: JWT authentication token
            department_id: Department ID
            
        Returns:
            Department dictionary with units
            
        Raises:
            HTTPException: If department not found
        """
        departments = await self.get_departments(token)
        
        for dept in departments:
            if dept.get("id") == department_id:
                return dept
        
        raise HTTPException(
            status_code=404,
            detail=f"Department {department_id} not found"
        )
    
    # ===== 3. Class Lecturers API =====
    
    async def get_lecturer_classes(
        self,
        token: str,
        lecturer_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get list of classes that a lecturer teaches.
        
        Endpoint: GET /api/v1/classes/lecturer/{lecturerId}
        
        Args:
            token: JWT authentication token
            lecturer_id: Lecturer user ID
            
        Returns:
            List of class dictionaries with keys: id, class_name, class_code, etc.
            
        Example:
            classes = await service.get_lecturer_classes(token, lecturer_id=2)
            # [{"id": 5, "class_name": "CNTT K15", "class_code": "CNTT15"}]
        """
        response = await self._make_request(
            "GET",
            f"/api/v1/classes/lecturer/{lecturer_id}",
            token
        )
        
        return response.get("data", [])
    
    async def check_lecturer_teaches_class(
        self,
        token: str,
        lecturer_id: int,
        class_id: int
    ) -> bool:
        """
        Check if a lecturer teaches a specific class.
        
        This is used for permission checks before allowing upload to class storage.
        
        Args:
            token: JWT authentication token
            lecturer_id: Lecturer user ID
            class_id: Class ID to check
            
        Returns:
            True if lecturer teaches the class, False otherwise
            
        Example:
            can_upload = await service.check_lecturer_teaches_class(token, 2, 5)
            if not can_upload:
                raise HTTPException(403, "You don't teach this class")
        """
        try:
            classes = await self.get_lecturer_classes(token, lecturer_id)
            class_ids = [c.get("id") for c in classes]
            return class_id in class_ids
        except Exception as e:
            logger.warning(f"Failed to check lecturer permission: {e}")
            # If API fails, allow access in dev (Laravel unavailable)
            # TODO: In production, change this to return False for security
            return True
    
    # ===== 4. Class Students API =====
    
    async def get_class_students(
        self,
        token: str,
        class_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get list of students in a class.
        
        Endpoint: GET /api/v1/student/class/{classId}
        
        Args:
            token: JWT authentication token
            class_id: Class ID
            
        Returns:
            List of student dictionaries with keys: id, full_name, email, student_code, etc.
            
        Example:
            students = await service.get_class_students(token, class_id=5)
            # [{"id": 1, "full_name": "Nguyễn Văn A", "student_code": "SV001"}]
        """
        response = await self._make_request(
            "GET",
            f"/api/v1/student/class/{class_id}",
            token
        )
        
        return response.get("data", [])
    
    # ===== 5. Notification API =====
    
    async def send_notification(
        self,
        token: str,
        user_id: int,
        title: str,
        message: str,
        type: str = "INFO",
        priority: str = "NORMAL",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send a notification to a single user.
        
        Endpoint: POST /api/v1/notifications/send
        
        Args:
            token: JWT authentication token
            user_id: User ID to send notification to
            title: Notification title
            message: Notification message
            type: Notification type (INFO, FILE_UPLOAD, SIGNING_APPROVED, etc.)
            priority: NORMAL, HIGH, or URGENT
            metadata: Additional data (links, IDs, etc.)
            
        Returns:
            Response from notification API
            
        Example:
            await service.send_notification(
                token=token,
                user_id=1,
                title="File mới",
                message="GV đã upload file",
                type="FILE_UPLOAD"
            )
        """
        json_data = {
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": type,
            "priority": priority,
            "metadata": metadata or {}
        }
        
        return await self._make_request(
            "POST",
            "/api/v1/notifications/send",
            token,
            json_data=json_data
        )
    
    async def send_notification_bulk(
        self,
        token: str,
        notifications: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Send multiple notifications at once (bulk).
        
        Endpoint: POST /api/v1/notifications/send-bulk
        
        Args:
            token: JWT authentication token
            notifications: List of notification dictionaries, each containing:
                - user_id (int)
                - title (str)
                - message (str)
                - type (str)
                - priority (str)
                - metadata (dict)
                
        Returns:
            Response from notification API
            
        Example:
            await service.send_notification_bulk(token, [
                {
                    "user_id": 1,
                    "title": "File mới",
                    "message": "...",
                    "type": "FILE_UPLOAD",
                    "priority": "NORMAL",
                    "metadata": {}
                },
                # ... more notifications
            ])
        """
        json_data = {"notifications": notifications}
        
        return await self._make_request(
            "POST",
            "/api/v1/notifications/send-bulk",
            token,
            json_data=json_data
        )
    
    async def notify_class_students(
        self,
        token: str,
        class_id: int,
        title: str,
        message: str,
        type: str = "FILE_UPLOAD",
        priority: str = "NORMAL",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Helper method to notify all students in a class.
        
        This combines get_class_students + send_notification_bulk.
        
        Args:
            token: JWT authentication token
            class_id: Class ID
            title: Notification title
            message: Notification message
            type: Notification type (default: FILE_UPLOAD)
            priority: Notification priority (default: NORMAL)
            metadata: Additional data
            
        Returns:
            Response from notification API, or None if no students found
            
        Example:
            await service.notify_class_students(
                token=token,
                class_id=5,
                title="File mới trong lớp CNTT K15",
                message="GV Trần Thị B đã upload Slide.pdf",
                metadata={"drive_item_id": "abc-123"}
            )
        """
        # 1. Get list of students
        students = await self.get_class_students(token, class_id)
        
        if not students:
            logger.warning(f"No students found in class {class_id}")
            return None
        
        # 2. Create notifications payload for each student
        notifications = [
            {
                "user_id": student.get("id"),
                "title": title,
                "message": message,
                "type": type,
                "priority": priority,
                "metadata": metadata or {}
            }
            for student in students
        ]
        
        # 3. Send bulk notifications
        logger.info(f"Sending notifications to {len(notifications)} students in class {class_id}")
        return await self.send_notification_bulk(token, notifications)


# ===== Singleton Instance =====

# Get System-Management URL from environment variable
SYSTEM_MANAGEMENT_URL = os.getenv(
    "SYSTEM_MANAGEMENT_URL",
    "http://localhost:8000"  # Default for local development
)

# Create singleton instance
system_management_service = SystemManagementService(
    base_url=SYSTEM_MANAGEMENT_URL
)

logger.info(f"System-Management service configured with URL: {SYSTEM_MANAGEMENT_URL}")
