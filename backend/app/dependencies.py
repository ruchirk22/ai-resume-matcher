# backend/app/dependencies.py
from fastapi import Depends, HTTPException, status, Header
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from . import crud, schemas, security
from .database import get_db

def get_current_user(authorization: str | None = Header(default=None, alias="Authorization"), db: Session = Depends(get_db)):
    """Simplified auth dependency: directly parse Bearer token from Authorization header.

    This removes the need for the OAuth2PasswordBearer flow (we already issue a JWT via /auth/login).
    Maintains identical response semantics while reducing indirection.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise credentials_exception
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    user = crud.get_user_by_email(db, email=token_data.email)
    if user is None:
        raise credentials_exception
    return user
