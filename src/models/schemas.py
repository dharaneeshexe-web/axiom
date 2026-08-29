from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class PaymentMethod(str, Enum):
    CARD = "card"
    UPI = "upi"
    NETBANKING = "netbanking"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


class OrderStatus(str, Enum):
    CREATED = "created"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CartItem(BaseModel):
    item_id: str
    name: str
    quantity: int
    price: int  # in paise (₹50 = 5000)
    merchant_id: str


class Intent(BaseModel):
    raw_query: str
    item: Optional[str] = None
    quantity: Optional[str] = None
    merchant: Optional[str] = None
    payment_method: Optional[PaymentMethod] = None
    confirmed: bool = False
    color: Optional[str] = None
    storage: Optional[str] = None
    size: Optional[str] = None
    flavor: Optional[str] = None


class Product(BaseModel):
    item_id: str
    name: str
    description: str
    price: int  # in paise
    merchant_id: str
    merchant_name: str
    in_stock: bool = True
    category: Optional[str] = None
    emoji: Optional[str] = None
    color: Optional[str] = None
    storage: Optional[str] = None
    size: Optional[str] = None
    flavor: Optional[str] = None
    weight: Optional[str] = None


class Order(BaseModel):
    order_id: str
    amount: int  # in paise
    currency: str = "INR"
    status: OrderStatus
    items: List[CartItem]
    merchant_id: str
    customer_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Payment(BaseModel):
    payment_id: str
    order_id: str
    amount: int
    currency: str = "INR"
    method: PaymentMethod
    status: PaymentStatus
    error_code: Optional[str] = None
    error_description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    captured_at: Optional[datetime] = None
    alias: Optional[str] = None


class AgentState(BaseModel):
    user_query: str
    intent: Optional[Intent] = None
    products: List[Product] = []
    selected_product: Optional[Product] = None
    order: Optional[Order] = None
    payment: Optional[Payment] = None
    error: Optional[str] = None
    retry_count: int = 0
    payment_method: PaymentMethod = PaymentMethod.CARD
    user_confirmed: bool = False
    trace_id: Optional[str] = None
