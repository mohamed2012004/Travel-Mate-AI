from fastapi import APIRouter, Depends, HTTPException, status

from database.base_database import UserRecord
from router.auth_schemas import AuthLogin, AuthRegister, Token, UserOut
from utils.auth import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(body: AuthRegister):
    from utils.backend_helpers import database

    existing = await database.get_user_by_email(body.email)
    if existing is not None:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    try:
        user = await database.create_user(body.email, hash_password(body.password))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"access_token": create_access_token(user.email), "token_type": "bearer"}


@router.post("/login", response_model=Token)
async def login(body: AuthLogin):
    from utils.backend_helpers import database

    user = await database.get_user_by_email(body.email)
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return {"access_token": create_access_token(user.email), "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
async def me(current_user: UserRecord = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email, "is_active": current_user.is_active}
