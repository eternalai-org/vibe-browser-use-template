from pydantic import BaseModel
from enum import Enum 
from typing import Optional, List, Union

class RunningStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    ERROR = "error"

class MarketCategory(str, Enum):
    ALL = "all"
    CRYPTO = "crypto"
    POLITICS = "politics"
    SPORTS = "sports"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"

class MarketSorting(str, Enum):
    VOLUME = "volume"
    NEWEST = "newest"
    ENDING_SOON = "ending_soon"

class MarketFrequency(str, Enum):
    ALL = "all"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

class Market(BaseModel):
    id: str
    name: str
    category: MarketCategory
    current_price: float
    volume: float
    end_date: Optional[str] = None

class MarketList(BaseModel):
    markets: List[Market]

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderRequest(BaseModel):
    market_id: str
    type: OrderType
    side: OrderSide
    amount: float
    price: Optional[float] = None  # Required for limit orders

class OrderResponse(BaseModel):
    order_id: str
    status: str
    filled_amount: float
    average_price: float

# custom agent's final answer structure here
class FinalAgentResult(BaseModel):
    status: RunningStatus = RunningStatus.DONE 
    message: str
