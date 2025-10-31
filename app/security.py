import os
import base64
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import EmailStr
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from .config import settings

# Importamos models y schemas, PERO NO 'crud' (para evitar importación circular)
from . import schemas, models
from .database import get_db

# Configuración de Hashing (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Esquema de autenticación (le dice a FastAPI cómo esperar el token)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")

# Secretos del .env
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    Hashea un password, asegurándose de truncarlo a 72 bytes
    para cumplir con la limitación de bcrypt.
    """
    password_bytes = password.encode('utf-8')
    truncated_bytes = password_bytes[:72]
    password_to_hash = truncated_bytes.decode('utf-8', 'ignore')
    return pwd_context.hash(password_to_hash)

# --- LÓGICA DE ENCRIPTACIÓN DE DATOS ---
# Cargamos la clave maestra del .env
MASTER_KEY = os.getenv("MASTER_ENCRYPTION_KEY")
if not MASTER_KEY:
    raise ValueError("MASTER_ENCRYPTION_KEY no está configurada en el .env")

try:
    # La clave en el .env (la nueva que te di) YA ESTÁ en el formato correcto.
    # Solo necesitamos codificarla a bytes para que Fernet la acepte.
    key_bytes = MASTER_KEY.encode('utf-8')

    # Fernet espera un string base64 de 44 bytes (que son 32 bytes de datos)
    if len(key_bytes) != 44:
        raise ValueError("La clave Fernet debe tener 44 caracteres.")

    # Creamos la instancia de Fernet
    fernet = Fernet(key_bytes)

except Exception as e:
    # Si la clave es inválida (ej. base64 corrupto), esto fallará
    raise ValueError(f"MASTER_ENCRYPTION_KEY es inválida o está corrupta: {e}")

def encrypt_data(data: str) -> str:
    """Encripta un string (API key, etc.) y devuelve un string encriptado."""
    if not data:
        return None
    encrypted_bytes = fernet.encrypt(data.encode('utf-8'))
    return encrypted_bytes.decode('utf-8')

def decrypt_data(encrypted_data: str) -> str:
    """Desencripta un string y devuelve el string original."""
    if not encrypted_data:
        return None
    try:
        decrypted_bytes = fernet.decrypt(encrypted_data.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        print(f"Error al desencriptar: {e}")
        return None

# --- LÓGICA DE TOKENS JWT ---

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    # ^^^^ ¡ARREGLADO! Se usa 'timedelta | None' en lugar de 'Optional[timedelta]'
    
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_db)
) -> models.User:
    
    # --- ¡ARREGLADO! Importamos 'crud' aquí dentro para evitar el bucle ---
    from . import crud
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: EmailStr = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    
    user = crud.get_user_by_email(db, email=token_data.email)
    if user is None:
        raise credentials_exception
    
    return user

async def get_current_active_user(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return current_user