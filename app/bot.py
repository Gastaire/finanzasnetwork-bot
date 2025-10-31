import pandas as pd
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- 1. IMPORTACIONES ACTUALIZADAS ---
from sqlalchemy.orm import Session
from .database import get_db
from .models import KLine, User
from .security import get_current_active_user
# ¡Importamos las estrategias desde nuestro motor de trading!
from .trading_engine import STRATEGY_REGISTRY, BaseStrategy

# --- 2. MODELOS PYDANTIC FLEXIBLES ---

class BacktestRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    interval: str = Field(...)
    strategy_name: str = Field(..., description="Nombre de la estrategia a usar (ej. 'RSI', 'MACD')")
    strategy_params: Dict[str, Any] = Field(default_factory=dict, description="Parámetros para la estrategia")
    initial_capital: float = Field(1000.0, gt=0)
    position_size: float = Field(1.0, gt=0, le=1)

class Trade(BaseModel):
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    profit: float
    profit_pct: float
    shares: float

class BacktestResult(BaseModel):
    strategy_name: str # <-- Añadido para claridad
    symbol: str
    interval: str
    initial_capital: float
    final_capital: float
    profit_loss: float
    profit_loss_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: Optional[float] = None
    trades: List[Trade]


# --- <<< 2. FUNCIÓN DE CARGA DE DATOS ACTUALIZADA >>> ---
def load_data_kline(symbol: str, interval: str, db: Session) -> pd.DataFrame:
    """
    Función SÍNCRONA para cargar datos de velas desde la base de datos.
    """
    print(f"Cargando datos REALES para {symbol} en {interval} desde la BBDD...")
    
    try:
        # Construir la consulta a la BBDD
        query = (
            db.query(
                KLine.timestamp,
                KLine.open,
                KLine.high,
                KLine.low,
                KLine.close,
                KLine.volume
            )
            .filter(KLine.symbol == symbol, KLine.interval == interval)
            .order_by(KLine.timestamp.asc())
        )
        
        # Usar pandas para leer la consulta SQL (muy eficiente)
        df = pd.read_sql_query(query.statement, db.bind)
        
        if df.empty:
            print("Advertencia: No se encontraron datos en la BBDD.")
            return df
            
        # Convertir y establecer el índice de tiempo
        # (read_sql_query ya debería traerlos como objetos datetime)
        df.set_index('timestamp', inplace=True)
        
        return df
        
    except Exception as e:
        print(f"Error al cargar datos de la BBDD: {e}")
        # Propagar el error para que el endpoint lo maneje
        raise e


# --- Funciones de Métricas (Sin cambios) ---

def get_annualization_factor(interval: str) -> float:
    interval = interval.lower()
    if 'm' in interval:
        minutes = int(interval.replace('m', ''))
        return (365 * 24 * 60 / minutes) ** 0.5
    elif 'h' in interval:
        hours = int(interval.replace('h', ''))
        return (365 * 24 / hours) ** 0.5
    elif 'd' in interval:
        days = int(interval.replace('d', ''))
        return (365 / days) ** 0.5
    return (365) ** 0.5

def calculate_metrics(trades: List[Trade], initial_capital: float, 
                     equity_curve: List[float], interval: str) -> dict:
    if not trades:
        return {'winning_trades': 0, 'losing_trades': 0, 'win_rate': 0.0, 
                'max_drawdown': 0.0, 'sharpe_ratio': None}
    
    winning_trades = sum(1 for t in trades if t.profit > 0)
    losing_trades = sum(1 for t in trades if t.profit <= 0)
    win_rate = (winning_trades / len(trades)) * 100 if trades else 0
    
    peak = initial_capital
    max_dd = 0
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak
        if dd > max_dd:
            max_dd = dd
    
    sharpe = None
    if len(equity_curve) > 1:
        returns = pd.Series(equity_curve).pct_change().dropna()
        if returns.std() > 0:
            annualization_factor = get_annualization_factor(interval)
            sharpe = (returns.mean() / returns.std()) * annualization_factor
        else:
            sharpe = 0
    
    return {'winning_trades': winning_trades, 'losing_trades': losing_trades, 
            'win_rate': win_rate, 'max_drawdown': max_dd * 100, 
            'sharpe_ratio': round(sharpe, 2) if sharpe is not None else None}


# --- Definición del Router ---
router = APIRouter()


# --- 3. ENDPOINT DE BACKTEST REFACTORIZADO ---
@router.post("/backtest", response_model=BacktestResult)
async def run_backtest(
    request: BacktestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Ejecuta un backtest para una estrategia de trading específica.
    """
    try:
        # 1. Seleccionar la estrategia dinámicamente
        StrategyClass = STRATEGY_REGISTRY.get(request.strategy_name)
        if not StrategyClass:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Estrategia '{request.strategy_name}' no encontrada.")
        
        # Instanciar con los parámetros proporcionados
        strategy: BaseStrategy = StrategyClass(**request.strategy_params)

        # 2. Cargar datos (sin cambios)
        df = await run_in_threadpool(load_data_kline, symbol=request.symbol, interval=request.interval, db=db)
        if df.empty:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No se encontraron datos para el símbolo y el intervalo.")
        
        # 3. Generar señales usando la estrategia seleccionada
        df = strategy.generate_signals(df)
        df.dropna(inplace=True) # Limpiar NaNs generados por los indicadores

        if df.empty:
            raise HTTPException(status_code=400, detail="No hay suficientes datos para calcular indicadores con los parámetros dados.")

        # 4. Bucle de backtesting genérico (basado en la columna 'signal')
        capital = request.initial_capital
        position = 0
        trades_list = []
        equity_curve = [capital]
        entry_price = 0.0
        entry_time = None

        for index, row in df.iterrows():
            current_price = row['close']
            signal = row['signal']

            # Señal de COMPRA
            if position == 0 and signal == 'BUY' and capital > 0:
                amount_to_invest = capital * request.position_size
                position = amount_to_invest / current_price
                capital -= amount_to_invest
                entry_price = current_price
                entry_time = index
                
            # Señal de VENTA
            elif position > 0 and signal == 'SELL':
                exit_price = current_price
                exit_time = index
                sale_value = position * exit_price
                capital += sale_value
                profit = sale_value - (position * entry_price)
                profit_pct = ((exit_price - entry_price) / entry_price) * 100
                
                trades_list.append(Trade(
                    entry_time=entry_time.isoformat(), exit_time=exit_time.isoformat(),
                    entry_price=round(entry_price, 2), exit_price=round(exit_price, 2),
                    profit=round(profit, 2), profit_pct=round(profit_pct, 2),
                    shares=round(position, 4)
                ))
                position = 0
            
            current_equity = capital + (position * current_price)
            equity_curve.append(current_equity)
        
        # ... (Lógica final para cerrar posición y calcular métricas, sin cambios)
        if position > 0:
            final_price = df.iloc[-1]['close']
            sale_value = position * final_price
            capital += sale_value
            profit = sale_value - (position * entry_price)
            profit_pct = ((final_price - entry_price) / entry_price) * 100
            trades_list.append(Trade(
                entry_time=entry_time.isoformat(), exit_time=df.index[-1].isoformat(),
                entry_price=round(entry_price, 2), exit_price=round(final_price, 2),
                profit=round(profit, 2), profit_pct=round(profit_pct, 2),
                shares=round(position, 4)
            ))
        
        final_capital = capital
        total_profit = final_capital - request.initial_capital
        total_profit_pct = (total_profit / request.initial_capital) * 100
        metrics = calculate_metrics(trades_list, request.initial_capital, equity_curve, request.interval)
        
        # Devolvemos el resultado, incluyendo el nombre de la estrategia
        return BacktestResult(
            strategy_name=strategy.name, # <-- Añadido
            symbol=request.symbol,
            interval=request.interval,
            initial_capital=round(request.initial_capital, 2),
            final_capital=round(final_capital, 2),
            profit_loss=round(total_profit, 2),
            profit_loss_pct=round(total_profit_pct, 2),
            total_trades=len(trades_list),
            winning_trades=metrics['winning_trades'],
            losing_trades=metrics['losing_trades'],
            win_rate=round(metrics['win_rate'], 2),
            max_drawdown=round(metrics['max_drawdown'], 2),
            sharpe_ratio=metrics['sharpe_ratio'],
            trades=trades_list
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Error de validación: {str(e)}")
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"Error: Columna faltante o parámetro de estrategia incorrecto - {str(e)}")
    except Exception as e:
        print(f"Error inesperado en backtest: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")


@router.get("/health", tags=["Bot Trading"]) # Agregado el tag
async def health_check():
    return {"status": "ok", "service": "backtest", "version": "1.1.0"}