from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from . import crud, schemas, security, models
from .database import get_db

router = APIRouter()

@router.post("/settings/api-keys", response_model=schemas.APIKeyResponse)
def save_api_keys(
    key_data: schemas.APIKeyCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """
    Recibe y guarda (o actualiza) las claves de API de un usuario, encriptándolas.
    """
    
    # Encriptamos los datos nuevos
    encrypted_key = security.encrypt_data(key_data.api_key)
    encrypted_secret = security.encrypt_data(key_data.api_secret)
    
    # --- LÓGICA DE ACTUALIZACIÓN ---
    # Buscamos si ya existe una clave para este usuario y broker
    db_key = db.query(models.ApiKey).filter(
        models.ApiKey.owner_id == current_user.id,
        models.ApiKey.broker_name == key_data.broker_name
    ).first()

    if db_key:
        # Si existe, la actualizamos
        db_key.encrypted_api_key = encrypted_key
        db_key.encrypted_api_secret = encrypted_secret
    else:
        # Si no existe, creamos una nueva
        db_key = models.ApiKey(
            broker_name=key_data.broker_name,
            encrypted_api_key=encrypted_key,
            encrypted_api_secret=encrypted_secret,
            owner_id=current_user.id
        )
        db.add(db_key)
    
    db.commit()
    db.refresh(db_key)
    
    return {"broker_name": db_key.broker_name, "is_saved": True}

@router.get("/settings/api-keys/status", response_model=schemas.APIKeyResponse)
def get_api_key_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """
    Verifica si el usuario actual ya tiene claves de PPI guardadas.
    No devuelve las claves, solo un estado.
    """
    # Buscamos si existe una clave de 'ppi' para este usuario
    db_key = db.query(models.ApiKey).filter(
        models.ApiKey.owner_id == current_user.id,
        models.ApiKey.broker_name == "ppi"
    ).first()

    if not db_key:
        return {"broker_name": "ppi", "is_saved": False}

    return {"broker_name": "ppi", "is_saved": True}