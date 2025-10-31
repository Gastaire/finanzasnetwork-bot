import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from . import crud, schemas, security, models
from .database import get_db

router = APIRouter()

# URL base de la API Sandbox de PPI
PPI_SANDBOX_URL = "https://clientapi_sandbox.portfoliopersonal.com"

@router.get("/portfolio/account-summary")
async def get_account_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """
    Obtiene el resumen de la cuenta (saldo) desde la API de PPI Sandbox.
    Este endpoint valida que las claves guardadas funcionen.
    """
    
    # 1. Buscar las claves del usuario en nuestra BBDD
    db_key = db.query(models.ApiKey).filter(
        models.ApiKey.owner_id == current_user.id,
        models.ApiKey.broker_name == "ppi"
    ).first()

    if not db_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontraron claves de API de PPI. Por favor, configúralas."
        )

    # 2. Desencriptar las claves
    try:
        api_key = security.decrypt_data(db_key.encrypted_api_key)
        api_secret = security.decrypt_data(db_key.encrypted_api_secret)
        if not api_key or not api_secret:
            raise Exception("Error de desencriptación")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al desencriptar claves. Vuelve a guardarlas."
        )

    # 3. Autenticarse contra la API de PPI (Obtener Token de PPI)
    # (La documentación de PPI indica que se necesita un token)
    # (Por ahora, simularemos este paso. Luego lo haremos real)
    
    # --- SIMULACIÓN (Borrar esto después) ---
    if api_key == "test_key_123" and api_secret == "test_secret_xyz":
        return {
            "entorno": "Sandbox (Simulado)",
            "moneda": "ARS",
            "saldo": 100000.00,
            "mensaje": "¡Conexión exitosa!"
        }
    else:
        # Esto responde a tu pregunta: "¿Si no son correctas?"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Claves de API de PPI inválidas (simulación)."
        )
    
    # --- CÓDIGO REAL (Próximamente) ---
    # async with httpx.AsyncClient() as client:
    #     try:
    #         # Paso A: Obtener token de PPI (ej. /auth/login)
    #         # auth_response = await client.post(f"{PPI_SANDBOX_URL}/api/auth/login", data={...})
    #         # ppi_token = auth_response.json()['token']
    #         
    #         # Paso B: Llamar al endpoint de cuenta con ese token
    #         # headers = {"Authorization": f"Bearer {ppi_token}"}
    #         # response = await client.get(f"{PPI_SANDBOX_URL}/api/v1/accounts", headers=headers)
    #         # response.raise_for_status()
    #         # return response.json()
    #     except httpx.HTTPStatusError as e:
    #         raise HTTPException(
    #             status_code=e.response.status_code,
    #             detail=f"Error desde la API de PPI: {e.response.text}"
    #         )