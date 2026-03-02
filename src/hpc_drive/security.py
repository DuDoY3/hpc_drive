import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy.orm import Session  # Import Session from sqlalchemy.orm

from .config import settings
from .database import get_session
from .models import User, UserRole  # Our local SQLModel User
from .schemas import AuthMeResponse, UserDataFromAuth  # The new schemas

# This just extracts the "Bearer <token>" string
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def map_role(user_type: str, is_admin: bool) -> UserRole:
    """
    Converts the auth service's role names into our local UserRole enum
    """
    if is_admin:
        return UserRole.ADMIN
    if user_type == "lecturer":
        return UserRole.TEACHER
    # Default to STUDENT
    return UserRole.STUDENT


def get_current_user_data_from_auth(
    token: str = Depends(oauth2_scheme),
) -> UserDataFromAuth:
    """
    Dependency that calls the Auth Service to validate the token
    and get up-to-date user info.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    headers = {"Authorization": f"Bearer {token}"}

    try:
        # Use httpx to make the request to the auth service
        with httpx.Client() as client:
            response = client.get(settings.AUTH_SERVICE_ME_URL, headers=headers)

        if response.status_code == 200:
            # Token is valid, parse the response
            auth_response = AuthMeResponse(**response.json())
            return auth_response.data  # Return just the 'data' block

        elif response.status_code == 401:
            # Token is invalid or expired
            raise credentials_exception

        elif response.status_code == 404:
            # User not found in auth service database - treat as invalid credentials
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        else:
            # Auth service might be down or returned another error
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Auth service error: {response.status_code}",
            )

    except (httpx.RequestError, ValidationError) as e:
        # Failed to connect to auth service or parse its response
        print(f"Error calling auth service: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not connect to authentication service",
        )


def get_current_user(
    session: Session = Depends(get_session),
    user_data: UserDataFromAuth = Depends(get_current_user_data_from_auth),
) -> User:
    """
    Primary dependency for endpoints.

    Gets validated user data from the auth service, syncs it to our
    local database, and returns the local 'User' object.
    """

    # user_data.id comes from the Auth Service JSON response
    user = session.get(User, user_data.id)

    new_role = map_role(user_data.user_type, user_data.account.is_admin)

    if user is None:
        # User does not exist locally, create them
        print(f"User not found locally (ID: {user_data.id}). Syncing new user...")

        # ***** CORRECTED TO SNAKE_CASE *****
        user = User(
            user_id=user_data.id,
            username=user_data.account.username,
            email=user_data.email,
            role=new_role,
        )
        session.add(user)

    else:
        # User exists, check if our local data is stale and update if needed
        update_made = False
        if user.username != user_data.account.username:
            user.username = user_data.account.username
            update_made = True
        if user.email != user_data.email:
            user.email = user_data.email
            update_made = True
        if user.role != new_role:
            user.role = new_role
            update_made = True
            
        # Ensure storage fields are initialized (for existing users after migration)
        if user.storage_quota is None:
            user.storage_quota = 10737418240 # 10GB
            update_made = True
        if user.used_storage is None:
            user.used_storage = 0
            update_made = True
        if user.max_file_size is None:
            user.max_file_size = 2147483648 # 2GB
            update_made = True

        if update_made:
            print(
                f"User data for {user.username} (ID: {user.user_id}) was stale. Updating..."
            )
            session.add(user)

    try:
        session.commit()
        session.refresh(user)
    except Exception as e:
        session.rollback()
        import sqlite3
        from sqlalchemy.exc import IntegrityError
        # Handle parallel requests race condition (another request inserted the user)
        if isinstance(e, IntegrityError) or "UNIQUE constraint failed" in str(e):
            print(f"Parallel insert detected for user {user_data.id}, falling back to fetch.")
            user = session.get(User, user_data.id)
            if user:
                return user
                
        print(f"Error committing user sync: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync user profile to local DB",
        )

    return user


def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    A dependency that ensures the current user is an admin.
    Raises a 403 Forbidden error if not.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action",
        )
    return current_user