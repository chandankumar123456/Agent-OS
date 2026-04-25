from fastapi import APIRouter, HTTPException, Depends
from uuid import uuid4
from ...auth.utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    generate_api_key,
    get_password_strength
)
from ...memory.long_term import user_repo
from ...api.schemas.user import UserCreate, UserResponse, LoginRequest, TokenResponse, RefreshTokenRequest
from ...logs.logger import logger

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse)
async def signup(request: UserCreate):
    existing_user = await user_repo.get_by_email(request.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    if not get_password_strength(request.password):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters with uppercase, lowercase, and digit"
        )
    
    user_id = str(uuid4())
    hashed_password = hash_password(request.password)
    api_key = generate_api_key()
    
    try:
        user = await user_repo.create(
            user_id=user_id,
            email=request.email,
            hashed_password=hashed_password,
            name=request.name,
            api_key=api_key,
            role="user"
        )
        
        access_token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
        refresh_token = create_refresh_token({"sub": user.id, "email": user.email, "role": user.role})
        
        logger.info(f"User signup: {request.email}")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            api_key=api_key,
            user=UserResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                role=user.role,
                created_at=user.created_at
            )
        )
    except Exception as e:
        logger.error(f"Signup failed: {e}")
        raise HTTPException(status_code=500, detail="Signup failed")


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    user = await user_repo.get_by_email(request.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.api_key:
        api_key = generate_api_key()
        user = await user_repo.update_api_key(user.id, api_key)
    
    access_token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    refresh_token = create_refresh_token({"sub": user.id, "email": user.email, "role": user.role})
    
    logger.info(f"User login: {request.email}")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        api_key=user.api_key,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            created_at=user.created_at
        )
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshTokenRequest):
    from ...auth.utils import verify_access_token
    payload = verify_access_token(request.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await user_repo.get_by_id(str(payload["sub"]))
    if not user or not getattr(user, "is_active", True):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    access_token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    refresh_token = create_refresh_token({"sub": user.id, "email": user.email, "role": user.role})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        api_key=user.api_key,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            created_at=user.created_at
        )
    )
