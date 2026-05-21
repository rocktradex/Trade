import os
import json
import uuid
import shutil
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import engine, get_db, Base
from models import Car, Settings
from schemas import (
    CarCreate, CarUpdate, CarOut, CalculatorInput, CalculatorResult,
    SettingsOut, SettingsUpdate,
)
import calc as calc_lib

# ──────────────────────────────────────────
Base.metadata.create_all(bind=engine)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AutoChina Marketplace", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ── helpers ───────────────────────────────

def get_settings(db: Session) -> Settings:
    s = db.query(Settings).filter(Settings.id == 1).first()
    if not s:
        s = Settings(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def require_admin(x_admin_password: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    settings = get_settings(db)
    if x_admin_password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Неверный пароль")


def car_to_out(car: Car) -> dict:
    data = {c.name: getattr(car, c.name) for c in Car.__table__.columns}
    data["photos"] = car.photos
    data["price_rub"] = car.price_rub
    data["total_price"] = car.total_price
    return data


# ══════════════════════════════════════════
# PUBLIC
# ══════════════════════════════════════════

@app.get("/api/cars", response_model=List[CarOut])
def list_cars(
    brand: Optional[str] = None,
    engine_type: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    price_max: Optional[float] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Car).filter(Car.available == 1)
    if brand:
        q = q.filter(Car.brand.ilike(f"%{brand}%"))
    if engine_type:
        q = q.filter(Car.engine_type == engine_type)
    if year_min:
        q = q.filter(Car.year >= year_min)
    if year_max:
        q = q.filter(Car.year <= year_max)
    if status:
        q = q.filter(Car.status == status)
    cars = q.order_by(Car.created_at.desc()).all()
    result = [car_to_out(c) for c in cars]
    if price_max:
        result = [c for c in result if c["total_price"] <= price_max]
    return result


@app.get("/api/cars/brands", response_model=List[str])
def list_brands(db: Session = Depends(get_db)):
    rows = db.query(Car.brand).filter(Car.available == 1).distinct().all()
    return sorted(set(r[0] for r in rows))


@app.get("/api/cars/{car_id}", response_model=CarOut)
def get_car(car_id: int, db: Session = Depends(get_db)):
    car = db.query(Car).filter(Car.id == car_id, Car.available == 1).first()
    if not car:
        raise HTTPException(status_code=404, detail="Авто не найдено")
    return car_to_out(car)


@app.get("/api/settings/public", response_model=SettingsOut)
def public_settings(db: Session = Depends(get_db)):
    return get_settings(db)


@app.post("/api/calculator", response_model=CalculatorResult)
def calculate(data: CalculatorInput, db: Session = Depends(get_db)):
    s = get_settings(db)
    rate_cny = data.cny_rate or s.cny_rate
    is_elec = data.engine_type.lower() in ("электро", "electric", "ev")

    price_rub = round(data.price_cny * rate_cny)
    delivery_china = 30_000         # доставка до порта в Китае
    delivery_russia = round(s.delivery_base)

    customs_value = price_rub + delivery_china + delivery_russia
    duty = calc_lib.customs_duty(customs_value, data.engine_volume, data.year, s.eur_rate, is_elec)
    fee = calc_lib.customs_fee(customs_value)
    recycling = calc_lib.recycling_fee(data.engine_volume, data.year, is_elec)
    sbkts = s.sbkts_cost
    other = 15_000  # оформление + страховка

    subtotal = price_rub + delivery_china + delivery_russia + duty + fee + recycling + sbkts + other
    commission = round(subtotal * s.commission_pct / 100)
    total = subtotal + commission

    note = ""
    if is_elec:
        note = "Для электромобилей таможенная пошлина временно 0%. Утилизационный сбор снижен."

    return CalculatorResult(
        brand=data.brand,
        model=data.model,
        year=data.year,
        price_cny=data.price_cny,
        cny_rate=rate_cny,
        price_rub=price_rub,
        delivery_china=delivery_china,
        delivery_russia=delivery_russia,
        customs_duty=duty,
        customs_fee=fee,
        sbkts=sbkts,
        recycling_fee=recycling,
        other_expenses=other,
        commission=commission,
        total_price=total,
        note=note,
    )


# ══════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════

@app.post("/api/admin/login")
def admin_login(body: dict, db: Session = Depends(get_db)):
    s = get_settings(db)
    if body.get("password") != s.admin_password:
        raise HTTPException(status_code=401, detail="Неверный пароль")
    return {"token": s.admin_password}


@app.get("/api/admin/cars", response_model=List[CarOut], dependencies=[Depends(require_admin)])
def admin_list_cars(db: Session = Depends(get_db)):
    return [car_to_out(c) for c in db.query(Car).order_by(Car.created_at.desc()).all()]


@app.post("/api/admin/cars", response_model=CarOut, dependencies=[Depends(require_admin)])
def admin_create_car(data: CarCreate, db: Session = Depends(get_db)):
    car = Car(**data.model_dump())
    car.photos = []
    db.add(car)
    db.commit()
    db.refresh(car)
    return car_to_out(car)


@app.put("/api/admin/cars/{car_id}", response_model=CarOut, dependencies=[Depends(require_admin)])
def admin_update_car(car_id: int, data: CarUpdate, db: Session = Depends(get_db)):
    car = db.query(Car).filter(Car.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="Не найдено")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(car, field, value)
    db.commit()
    db.refresh(car)
    return car_to_out(car)


@app.delete("/api/admin/cars/{car_id}", dependencies=[Depends(require_admin)])
def admin_delete_car(car_id: int, db: Session = Depends(get_db)):
    car = db.query(Car).filter(Car.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="Не найдено")
    for photo in car.photos:
        (UPLOAD_DIR / photo).unlink(missing_ok=True)
    db.delete(car)
    db.commit()
    return {"ok": True}


@app.post("/api/admin/cars/{car_id}/photos", dependencies=[Depends(require_admin)])
async def admin_upload_photos(car_id: int, files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    car = db.query(Car).filter(Car.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="Не найдено")
    names = list(car.photos)
    for f in files:
        ext = Path(f.filename).suffix.lower() or ".jpg"
        name = f"{uuid.uuid4().hex}{ext}"
        dest = UPLOAD_DIR / name
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        names.append(name)
    car.photos = names
    db.commit()
    return {"photos": names}


@app.delete("/api/admin/cars/{car_id}/photos/{filename}", dependencies=[Depends(require_admin)])
def admin_delete_photo(car_id: int, filename: str, db: Session = Depends(get_db)):
    car = db.query(Car).filter(Car.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="Не найдено")
    photos = [p for p in car.photos if p != filename]
    car.photos = photos
    db.commit()
    (UPLOAD_DIR / filename).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/admin/settings", response_model=SettingsOut, dependencies=[Depends(require_admin)])
def admin_get_settings(db: Session = Depends(get_db)):
    return get_settings(db)


@app.put("/api/admin/settings", response_model=SettingsOut, dependencies=[Depends(require_admin)])
def admin_update_settings(data: SettingsUpdate, db: Session = Depends(get_db)):
    s = get_settings(db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return s


# ── serve built React app ─────────────────
STATIC_DIR = Path("../frontend/dist")
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="spa")
