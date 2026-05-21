from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime


class CarBase(BaseModel):
    brand: str
    model: str
    year: int
    mileage: int = 0
    color: str = ""
    engine_volume: int = 0
    engine_type: str = "бензин"
    transmission: str = "автомат"
    drive: str = "передний"
    power: int = 0
    configuration: str = ""
    description: str = ""
    status: str = "в Китае"
    available: int = 1
    order_only: int = 0
    price_cny: float = 0
    cny_rate: float = 12.5
    delivery_china: float = 0
    delivery_russia: float = 0
    customs_duty: float = 0
    customs_fee: float = 0
    sbkts: float = 0
    recycling_fee: float = 0
    other_expenses: float = 0
    commission: float = 0


class CarCreate(CarBase):
    pass


class CarUpdate(CarBase):
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None


class CarOut(CarBase):
    id: int
    photos: List[str] = []
    price_rub: float
    total_price: float
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SettingsOut(BaseModel):
    cny_rate: float
    eur_rate: float
    delivery_base: float
    sbkts_cost: float
    commission_pct: float

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    cny_rate: Optional[float] = None
    eur_rate: Optional[float] = None
    delivery_base: Optional[float] = None
    sbkts_cost: Optional[float] = None
    commission_pct: Optional[float] = None
    admin_password: Optional[str] = None


class CalculatorInput(BaseModel):
    brand: str = ""
    model: str = ""
    year: int
    engine_volume: int           # куб.см
    engine_type: str = "бензин"  # электро → особый расчёт
    price_cny: float             # цена в Китае (юань)
    cny_rate: Optional[float] = None  # если не задан — берём из настроек


class CalculatorResult(BaseModel):
    brand: str
    model: str
    year: int
    price_cny: float
    cny_rate: float
    price_rub: float
    delivery_china: float
    delivery_russia: float
    customs_duty: float
    customs_fee: float
    sbkts: float
    recycling_fee: float
    other_expenses: float
    commission: float
    total_price: float
    note: str = ""
