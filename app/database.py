from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings # <-- Importamos la instancia centralizada

# --- USAMOS LA CONFIGURACIÓN CENTRAL ---
# La URL de la base de datos ahora viene de la instancia 'settings'
# que ya ha validado que la variable de entorno exista.
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Configuración del motor
engine_args = {}
# Seguimos necesitando esta lógica específica para SQLite
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