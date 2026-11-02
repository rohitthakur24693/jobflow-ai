import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import HTTPException, Header, Cookie, Depends, status

from config import AUTH_SECRET_KEY, AUTH_ALGORITHM, AUTH_TOKEN_EXPIRE_DAYS
from database import get_user_by_id

def create_access_token(user_id: str, email: str) -> str:
    """Generate a signed JWT token containing user_id and expiration."""
    exp = datetime.now(timezone.utc) + timedelta(days=AUTH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "email": email.strip().lower(),
        "iat": datetime.now(timezone.utc),
        "exp": exp
    }
    return jwt.encode(payload, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)

def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify JWT token signature and expiration."""
    if not token:
        return None
    try:
        # Strip 'Bearer ' if present
        clean_token = token.strip()
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()
            
        payload = jwt.decode(clean_token, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

async def get_current_user(
    authorization: Optional[str] = Header(None),
    jobflow_token: Optional[str] = Cookie(None)
) -> Dict[str, Any]:
    """
    FastAPI dependency that enforces strict authentication.
    Extracts token from Authorization Header or Cookie.
    Returns authenticated user record or raises 401 Unauthorized.
    """
    token = None
    if authorization and authorization.strip():
        token = authorization
    elif jobflow_token and jobflow_token.strip():
        token = jobflow_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in or create an account.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = verify_access_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid credentials. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return user

async def get_optional_user(
    authorization: Optional[str] = Header(None),
    jobflow_token: Optional[str] = Cookie(None)
) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency for endpoints that allow anonymous browsing
    but personalize when an authenticated session is provided.
    """
    token = authorization or jobflow_token
    if not token:
        return None
    payload = verify_access_token(token)
    if not payload or not payload.get("sub"):
        return None
    return get_user_by_id(payload["sub"])
