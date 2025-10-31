from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

# --- Importaciones Clave ---
from . import security, models
from .database import get_db
from ppi_client.ppi import PPI # La librería oficial de PPI

router = APIRouter()

# --- Modelos de Respuesta para el Frontend ---
# Definimos una estructura clara para la respuesta

class BalanceItem(BaseModel):
    currency: str
    settlement: str
    amount: float

class AccountSummaryResponse(BaseModel):
    environment: str
    account_number: str
    balances: List[BalanceItem]

# --- Lógica de Conexión (Síncrona) ---
# La librería ppi-client es síncrona, así que la aislamos en su propia función

def fetch_ppi_balance(
    account_number: str, 
    api_key: str, 
    api_secret: str
) -> List[dict]:
    """
    Función síncrona que se conecta a PPI y obtiene el balance.
    Esta función se ejecutará en un hilo separado.
    """
    try:
        # 1. Inicializar la librería en modo Sandbox
        ppi = PPI(sandbox=True)
        
        # 2. Autenticarse
        ppi.account.login_api(api_key, api_secret)
        
        # 3. Obtener el saldo disponible para la cuenta
        balances = ppi.account.get_available_balance(account_number)
        
        return balances
        
    except Exception as e:
        # Capturamos cualquier error de la librería (ej. credenciales inválidas)
        # y lo relanzamos para que el endpoint de FastAPI lo maneje.
        # Podríamos ser más específicos si la librería define excepciones propias.
        print(f"Error en la librería PPI: {e}")
        # Usamos un ValueError para señalar un problema de cliente/datos.
        raise ValueError(f"Error al conectar con PPI: {str(e)}")


# --- Endpoint Principal (Asíncrono) ---

@router.get("/portfolio/account-summary", response_model=AccountSummaryResponse)
async def get_account_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """
    Obtiene el resumen de la cuenta (saldo) real desde la API de PPI Sandbox.
    Este endpoint valida que las claves guardadas y el número de cuenta funcionen.
    """
    
    # 1. Buscar las claves y el número de cuenta del usuario en nuestra BBDD
    db_key = db.query(models.ApiKey).filter(
        models.ApiKey.owner_id == current_user.id,
        models.ApiKey.broker_name == "ppi"
    ).first()

    if not db_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontraron claves de API de PPI. Por favor, configúralas."
        )

    # 2. Desencriptar todos los datos necesarios
    try:
        account_number = security.decrypt_data(db_key.encrypted_account_number)
        api_key = security.decrypt_data(db_key.encrypted_api_key)
        api_secret = security.decrypt_data(db_key.encrypted_api_secret)
        
        if not all([account_number, api_key, api_secret]):
            raise ValueError("Datos de API corruptos o incompletos.")
            
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al desencriptar claves. Vuelve a guardarlas."
        )

    # 3. Ejecutar la función síncrona en un hilo separado
    try:
        # `run_in_threadpool` evita que la llamada a la API de PPI bloquee nuestra app
        ppi_balances = await run_in_threadpool(
            fetch_ppi_balance, 
            account_number=account_number, 
            api_key=api_key, 
            api_secret=api_secret
        )
        
        # 4. Formatear la respuesta para el frontend
        # La respuesta de PPI es una lista de dicts, la convertimos a nuestro modelo
        formatted_balances = [
            BalanceItem(
                currency=item.get("name", "N/A"),
                settlement=item.get("settlement", "N/A"),
                amount=item.get("amount", 0.0)
            ) for item in ppi_balances
        ]

        return AccountSummaryResponse(
            environment="Sandbox (Real)",
            account_number=account_number,
            balances=formatted_balances
        )

    except ValueError as e:
        # Este error viene de nuestra función `fetch_ppi_balance`
        # Usualmente indica credenciales inválidas o un error de la API de PPI.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        # Captura cualquier otro error inesperado
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor al procesar la solicitud: {str(e)}"
        )