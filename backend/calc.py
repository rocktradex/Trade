"""Расчёт таможенных платежей для коммерческого ввоза авто из Китая."""

from datetime import date


def customs_duty(customs_value_rub: float, engine_cc: int, car_year: int, eur_rate: float, is_electric: bool = False) -> float:
    """Таможенная пошлина по Единому таможенному тарифу ЕАЭС."""
    if is_electric:
        # Временная нулевая ставка для электромобилей (действует до 2025)
        return 0.0

    car_age = date.today().year - car_year

    if car_age < 3:
        # Новые / до 3 лет — ставка от объёма + 48% от ТС
        pct = 0.48
        rates = [
            (1000, 2.5),
            (1500, 2.7),
            (1800, 3.0),
            (3000, 3.6),
            (float("inf"), 5.6),
        ]
    else:
        # Старше 3 лет — 54% или ставка за куб.см
        pct = 0.54
        rates = [
            (1000, 1.4),
            (1500, 1.5),
            (1800, 1.6),
            (3000, 2.2),
            (float("inf"), 2.5),
        ]

    rate_per_cc = next(r for limit, r in rates if engine_cc <= limit)
    by_pct = customs_value_rub * pct
    by_cc = engine_cc * rate_per_cc * eur_rate
    return round(max(by_pct, by_cc))


def customs_fee(customs_value_rub: float) -> float:
    """Таможенный сбор (фиксированные ставки по ТС таможенной стоимости)."""
    tiers = [
        (200_000, 775),
        (450_000, 1_550),
        (1_200_000, 3_100),
        (2_500_000, 8_530),
        (5_000_000, 12_000),
        (10_000_000, 15_500),
        (float("inf"), 20_000),
    ]
    return next(fee for limit, fee in tiers if customs_value_rub <= limit)


def recycling_fee(engine_cc: int, car_year: int, is_electric: bool = False) -> float:
    """Утилизационный сбор для юридических лиц (коммерческий ввоз)."""
    BASE = 150_000
    car_age = date.today().year - car_year
    old = car_age >= 3

    if is_electric:
        coef = 0.26 if old else 0.17
    elif engine_cc <= 1000:
        coef = 6.15 if old else 1.65
    elif engine_cc <= 2000:
        coef = 15.69 if old else 4.2
    elif engine_cc <= 3000:
        coef = 24.01 if old else 6.3
    else:
        coef = 24.01 if old else 6.3

    return round(BASE * coef)
