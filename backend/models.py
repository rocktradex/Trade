import json
from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from sqlalchemy.sql import func
from database import Base


class Car(Base):
    __tablename__ = "cars"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, index=True, nullable=False)
    model = Column(String, index=True, nullable=False)
    year = Column(Integer, nullable=False)
    mileage = Column(Integer, default=0)
    color = Column(String, default="")
    engine_volume = Column(Integer, default=0)  # куб.см
    engine_type = Column(String, default="бензин")  # бензин/дизель/электро/гибрид
    transmission = Column(String, default="автомат")
    drive = Column(String, default="передний")
    power = Column(Integer, default=0)  # л.с.
    configuration = Column(String, default="")
    description = Column(Text, default="")
    photos_json = Column(Text, default="[]")  # JSON-список имён файлов
    status = Column(String, default="в Китае")
    # Статусы: в Китае / в пути / в Новороссийске / на таможне / готова к выдаче
    available = Column(Integer, default=1)  # 1=в каталоге, 0=скрыт
    order_only = Column(Integer, default=0)  # только под заказ

    # --- Разбивка цены ---
    price_cny = Column(Float, default=0)          # Цена в Китае (юань)
    cny_rate = Column(Float, default=12.5)         # Курс CNY/RUB
    delivery_china = Column(Float, default=0)      # Доставка по Китаю до порта
    delivery_russia = Column(Float, default=0)     # Фрахт + доставка до Новороссийска
    customs_duty = Column(Float, default=0)        # Таможенная пошлина
    customs_fee = Column(Float, default=0)         # Таможенный сбор
    sbkts = Column(Float, default=0)               # СБКТС (одобрение типа ТС)
    recycling_fee = Column(Float, default=0)       # Утилизационный сбор
    other_expenses = Column(Float, default=0)      # Прочие расходы
    commission = Column(Float, default=0)          # Комиссия

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    @property
    def photos(self):
        try:
            return json.loads(self.photos_json or "[]")
        except Exception:
            return []

    @photos.setter
    def photos(self, value):
        self.photos_json = json.dumps(value)

    @property
    def price_rub(self):
        return round((self.price_cny or 0) * (self.cny_rate or 12.5))

    @property
    def total_price(self):
        return round(sum([
            self.price_rub,
            self.delivery_china or 0,
            self.delivery_russia or 0,
            self.customs_duty or 0,
            self.customs_fee or 0,
            self.sbkts or 0,
            self.recycling_fee or 0,
            self.other_expenses or 0,
            self.commission or 0,
        ]))


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, default=1)
    cny_rate = Column(Float, default=12.5)
    eur_rate = Column(Float, default=95.0)
    delivery_base = Column(Float, default=180_000)   # базовая доставка до Новороссийска
    sbkts_cost = Column(Float, default=35_000)
    commission_pct = Column(Float, default=5.0)
    admin_password = Column(String, default="china2024")
