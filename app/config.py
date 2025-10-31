# app/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict
import os

# Determina la ruta al archivo .env
# Esto asume que .env está en el directorio raíz (junto a la carpeta 'app')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, '.env')


class Settings(BaseSettings):
    """
    Define y carga las variables de entorno de la aplicación.
    Pydantic-settings se encarga de leer el .env y validar los tipos.
    """
    
    # Configuración del cargador de .env
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,          # Le dice dónde buscar el .env
        env_file_encoding="utf-8",
        extra="ignore"              # Ignora otras variables de entorno
    )
    
    # --- Variables de Entorno Requeridas ---
    # Si alguna de estas falta en el .env, la app NO iniciará (lo cual es bueno)
    
    # Base de Datos
    DATABASE_URL: str
    
    # Autenticación (auth.py)
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    
    # Seguridad (security.py)
    MASTER_ENCRYPTION_KEY: str  # <--- ¡La variable problemática!

    # --- Opcionales con valor por defecto ---
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30


# --- Instancia Única ---
# Creamos una instancia única de la configuración.
# Todos los demás archivos importarán ESTA instancia.
# En el momento en que se crea esta instancia, pydantic lee y valida el .env.
try:
    settings = Settings()
except Exception as e:
    print(f"ERROR: No se pudieron cargar las variables de entorno. {e}")
    print(f"Asegúrate de que el archivo .env esté en {ENV_PATH}")
    raise e