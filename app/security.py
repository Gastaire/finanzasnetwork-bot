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

# --- ¡CAMBIO CLAVE! ---
# Importamos la instancia 'settings' desde config.
from .config import settings

# Importamos models y schemas, PERO NO 'crud' (para evitar importación circular)
from . import schemas, models
from .database import get_db

# Configuración de Hashing (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Esquema de autenticación (le dice a FastAPI cómo esperar el token)
# El tokenUrl ahora usa el prefijo completo definido en main.py
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Las variables ahora se leen desde la instancia 'settings'
# No es necesario definir SECRET_KEY, ALGORITHM, etc. aquí.

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
# Leemos la clave maestra desde la instancia 'settings'
MASTER_KEY = settings.MASTER_ENCRYPTION_KEY
if not MASTER_KEY:
    # Esta validación es redundante si Settings la marca como requerida, pero es una buena práctica de seguridad
    raise ValueError("MASTER_ENCRYPTION_KEY no está configurada.")

try:
    # La clave en el .env YA ESTÁ en el formato correcto (URL-safe base64).
    # Solo necesitamos codificarla a bytes para que Fernet la acepte.
    key_bytes = MASTER_KEY.encode('utf-8')

    if len(key_bytes) != 44:
        raise ValueError("La clave Fernet debe tener 44 caracteres.")

    # Creamos la instancia de Fernet
    fernet = Fernet(key_bytes)

except Exception as e:
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
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Usamos el valor desde 'settings'
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    # Usamos los valores desde 'settings'
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_db)
) -> models.User:
    
    from . import crud
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Usamos los valores desde 'settings'
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
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