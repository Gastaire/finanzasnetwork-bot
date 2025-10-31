from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Float, Index # <-- AÑADIR ESTOS
from sqlalchemy.orm import relationship
from .database import Base

class KLine(Base):
    """
    Modelo para almacenar los datos de velas (OHLCV).
    """
    __tablename__ = "klines"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    interval = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime, index=True, nullable=False, unique=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    __table_args__ = (
        # Índice compuesto para optimizar las búsquedas del backtester
        Index('ix_symbol_interval_timestamp', 'symbol', 'interval', 'timestamp'),
    )

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

    # --- AÑADIR ESTA LÍNEA ---
    api_keys = relationship("ApiKey", back_populates="owner")


# --- AÑADIR TODA ESTA CLASE NUEVA ---
class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    broker_name = Column(String, index=True, default="ppi") # Para el futuro (ej. IOL)
    
    # Guardamos los datos encriptados
    encrypted_account_number = Column(String, nullable=False) # <--- ¡NUEVO CAMPO!
    encrypted_api_key = Column(String, nullable=False)
    encrypted_api_secret = Column(String, nullable=False)
    
    # El 'owner_id' es el link a la tabla 'users'
    owner_id = Column(Integer, ForeignKey("users.id"))

    # La relación inversa
    owner = relationship("User", back_populates="api_keys")