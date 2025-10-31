from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings
import os # <-- Importamos OS para leer variables de entorno

# --- ROMPEMOS EL CICLO AQUÍ ---
# Ya no importamos 'settings'. Leemos la URL directamente
# (Asegúrate de tener esta variable en tu entorno o pon la URL aquí)
# EJ: SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"
# EJ: SQLALCHEMY_DATABASE_URL = "postgresql://user:password@localhost/dbname"

SQLALCHEMY_DATABASE_URL = os.environ.get(
    "DATABASE_URL", 
    "sqlite:///./sql_app.db" # <-- Valor por defecto si no la encuentra
)

# Configuración del motor
engine_args = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    **engine_args
)

# Configuración de la sesión
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para los modelos
# models.py importará ESTA variable
Base = declarative_base()


# Dependencia de FastAPI
def get_db():
    """
    Dependencia de FastAPI para obtener una sesión de BBDD.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()