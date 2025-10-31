import asyncio
from datetime import datetime
import pandas as pd
import pandas_ta as ta
from abc import ABC, abstractmethod
from fastapi import APIRouter

# --- Importaciones del proyecto ---
from .database import SessionLocal
from .models import KLine

router = APIRouter()

# --- 1. ESTRUCTURA DE ESTRATEGIAS MODULAR ---

class BaseStrategy(ABC):
    """
    Clase base abstracta para todas las estrategias de trading.
    Define el contrato que cualquier estrategia debe cumplir.
    """
    @abstractmethod
    def generate_signals(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Toma un DataFrame con datos de mercado (OHLCV) y debe devolver
        el mismo DataFrame con una columna adicional 'signal' que contenga
        'BUY', 'SELL' o 'HOLD'.
        """
        pass

# --- ESTRATEGIA #1: RSI (Reversión a la Media) ---
class RSIStrategy(BaseStrategy):
    def __init__(self, rsi_length: int = 14, rsi_buy: float = 30, rsi_sell: float = 70):
        self.rsi_length = rsi_length
        self.rsi_buy = rsi_buy
        self.rsi_sell = rsi_sell
        self.name = f"RSI({self.rsi_length}, {self.rsi_buy}, {self.rsi_sell})"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df['rsi'] = ta.rsi(df['close'], length=self.rsi_length)
        df['signal'] = 'HOLD'
        # Condición de compra: RSI cruza hacia arriba el umbral
        buy_conditions = (df['rsi'] < self.rsi_buy) & (df['rsi'].shift(1) >= self.rsi_buy)
        # Condición de venta: RSI cruza hacia abajo el umbral
        sell_conditions = (df['rsi'] > self.rsi_sell) & (df['rsi'].shift(1) <= self.rsi_sell)
        df.loc[buy_conditions, 'signal'] = 'BUY'
        df.loc[sell_conditions, 'signal'] = 'SELL'
        return df

# --- ESTRATEGIA #2: Cruce de Medias Móviles (Seguimiento de Tendencia) ---
class MACrossStrategy(BaseStrategy):
    def __init__(self, fast_period: int = 20, slow_period: int = 50):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.name = f"MACross({self.fast_period}, {self.slow_period})"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df['fast_ma'] = ta.sma(df['close'], length=self.fast_period)
        df['slow_ma'] = ta.sma(df['close'], length=self.slow_period)
        df['signal'] = 'HOLD'
        # Cruce dorado (Golden Cross): la rápida cruza hacia arriba a la lenta
        buy_conditions = (df['fast_ma'] > df['slow_ma']) & (df['fast_ma'].shift(1) <= df['slow_ma'].shift(1))
        # Cruce de la muerte (Death Cross): la rápida cruza hacia abajo a la lenta
        sell_conditions = (df['fast_ma'] < df['slow_ma']) & (df['fast_ma'].shift(1) >= df['slow_ma'].shift(1))
        df.loc[buy_conditions, 'signal'] = 'BUY'
        df.loc[sell_conditions, 'signal'] = 'SELL'
        return df

# --- ESTRATEGIA #3: MACD (Momentum y Tendencia) ---
class MACDStrategy(BaseStrategy):
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.name = f"MACD({self.fast}, {self.slow}, {self.signal})"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # pandas-ta devuelve un DataFrame con las columnas de MACD
        macd = ta.macd(df['close'], fast=self.fast, slow=self.slow, signal=self.signal)
        # Renombramos y unimos al DataFrame principal
        df = df.join(macd)
        df['signal'] = 'HOLD'
        # Condición de compra: MACD cruza hacia arriba la línea de señal
        buy_conditions = (df[f'MACD_{self.fast}_{self.slow}_{self.signal}'] > df[f'MACDs_{self.fast}_{self.slow}_{self.signal}']) & \
                         (df[f'MACD_{self.fast}_{self.slow}_{self.signal}'].shift(1) <= df[f'MACDs_{self.fast}_{self.slow}_{self.signal}'].shift(1))
        # Condición de venta: MACD cruza hacia abajo la línea de señal
        sell_conditions = (df[f'MACD_{self.fast}_{self.slow}_{self.signal}'] < df[f'MACDs_{self.fast}_{self.slow}_{self.signal}']) & \
                          (df[f'MACD_{self.fast}_{self.slow}_{self.signal}'].shift(1) >= df[f'MACDs_{self.fast}_{self.slow}_{self.signal}'].shift(1))
        df.loc[buy_conditions, 'signal'] = 'BUY'
        df.loc[sell_conditions, 'signal'] = 'SELL'
        return df


# --- 2. EL MOTOR DE TRADING (WORKER) ---

# --- ¡CONFIGURACIÓN DEL MOTOR! ---
# Cambia el string aquí para usar otra estrategia
STRATEGY_IN_USE = 'MACD' 
TRADING_WORKER_SLEEP_INTERVAL = 60
ASSET_TO_TRADE = ("GGAL", "1d")

# Registro de estrategias disponibles
STRATEGY_REGISTRY = {
    'RSI': RSIStrategy,
    'MA_CROSS': MACrossStrategy,
    'MACD': MACDStrategy,
}

async def trading_engine_worker():
    """
    El "cerebro" del bot. Este worker se ejecuta en un bucle,
    selecciona una estrategia, analiza los datos y decide qué acción tomar.
    """
    print(">>> Motor de Trading iniciado. <<<")

    # Seleccionar e instanciar la estrategia desde el registro
    StrategyClass = STRATEGY_REGISTRY.get(STRATEGY_IN_USE)
    if not StrategyClass:
        print(f"ERROR: Estrategia '{STRATEGY_IN_USE}' no encontrada. Deteniendo motor.")
        return
    strategy = StrategyClass()
    print(f"Motor: Usando la estrategia -> {strategy.name}")

    position_open = False

    while True:
        try:
            with SessionLocal() as db:
                print(f"[{datetime.now()}] Motor: Analizando {ASSET_TO_TRADE[0]} con {strategy.name}...")
                
                query = (
                    db.query(KLine)
                    .filter(KLine.symbol == ASSET_TO_TRADE[0], KLine.interval == ASSET_TO_TRADE[1])
                    .order_by(KLine.timestamp.desc())
                    .limit(200)
                )
                df = pd.read_sql_query(query.statement, db.bind).sort_values(by='timestamp')

                if df.empty or len(df) < 50: # Aumentamos el mínimo para medias móviles largas
                    print("Motor: No hay suficientes datos para analizar. Esperando...")
                    await asyncio.sleep(TRADING_WORKER_SLEEP_INTERVAL)
                    continue

                df_with_signals = strategy.generate_signals(df)
                
                # Ignoramos las señales que no sean la última
                last_signal_row = df_with_signals.iloc[-1]
                current_signal = last_signal_row['signal']
                
                print(f"Motor: Último precio de {ASSET_TO_TRADE[0]}: ${last_signal_row['close']:.2f}. Señal: {current_signal}.")

                if current_signal == 'BUY' and not position_open:
                    print("!!! DECISIÓN: COMPRAR. (Simulado) !!!")
                    position_open = True
                
                elif current_signal == 'SELL' and position_open:
                    print("!!! DECISIÓN: VENDER. (Simulado) !!!")
                    position_open = False
                
                else:
                    print("Motor: Decisión: MANTENER (HOLD).")

        except Exception as e:
            print(f"ERROR CRÍTICO en el motor de trading: {e}")
            await asyncio.sleep(120)

        await asyncio.sleep(TRADING_WORKER_SLEEP_INTERVAL)