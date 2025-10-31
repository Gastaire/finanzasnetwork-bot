from pydantic import BaseModel, EmailStr
from typing import Optional

# --- Token (Para Login) ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: EmailStr | None = None

# --- User (Para Registro y Perfil) ---
class UserBase(BaseModel):
    # Usamos EmailStr para que Pydantic valide automáticamente el email
    email: EmailStr

class UserCreate(UserBase):
    # El password solo se pide al crear
    password: str

class UserResponse(UserBase):
    # Esto es lo que devolvemos al frontend: NUNCA el password
    id: int
    is_active: bool

    class Config:
        orm_mode = True # Permite a Pydantic leer datos desde modelos de SQLAlchemy

class APIKeyBase(BaseModel):
    broker_name: str = "ppi"

class APIKeyCreate(APIKeyBase):
    api_key: str
    api_secret: str

class APIKeyResponse(BaseModel):
    """Respuesta segura para el frontend"""
    broker_name: str
    is_saved: bool = True


# --- Bot / Backtesting ---

class BacktestRequest(BaseModel):
    ticker: str
    strategy_name: str = "rsi_simple"
    years: int = 1
    
    # Parámetros específicos de la estrategia
    rsi_buy: int = 30
    rsi_sell: int = 70
    rsi_length: int = 14

class BacktestResult(BaseModel):
    ticker: str
    strategy: str
    period_years: int
    
    # Métricas de rendimiento
    total_profit_percent: float
    total_trades: int
    win_rate_percent: float
    
    # Comparativa
    buy_and_hold_profit_percent: float
    strategy_beat_market: bool