from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from . import crud, schemas, security, models
from .database import get_db

router = APIRouter()

@router.post("/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Endpoint para registrar un nuevo usuario.
    Valida que el email no exista.
    """
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya está registrado"
        )
    
    # schemas.UserCreate valida la entrada (sanitización)
    new_user = crud.create_user(db, user=user)
    
    # schemas.UserResponse filtra la salida (nunca devuelve el hash)
    return new_user

@router.post("/login", response_model=schemas.Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    """
    Endpoint para login. Devuelve un Token JWT.
    """
    user = crud.get_user_by_email(db, email=form_data.username) # OIDC usa "username"
    
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Creamos el token
    access_token = security.create_access_token(
        data={"sub": user.email} # "sub" es el estándar para "subject"
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/users/me", response_model=schemas.UserResponse)
async def read_users_me(
    current_user: models.User = Depends(security.get_current_active_user)
):
    """
    Endpoint protegido.
    Solo funciona si se envía un Token JWT válido.
    """
    return current_user