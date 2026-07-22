"""
calculator.py

The pricing logic — ported 1:1 from the original frontend script.js.
This is the ONLY place the formulas live now. The frontend never sees
DOLLAR_RATE, SHIPPING_PER_KG, the service-fee math, or the profit
margin — it only ever receives the final EGP total from /api/analyze.
"""

from typing import Optional

# ===================================================================
# EDITABLE RATES
# ===================================================================
DOLLAR_RATE = 54
SHIPPING_PER_KG = 405   # EGP per kg
DISCOUNT = 0.3          # 30% off, applied on the discounted branch (StyleKorean non-time-deal)
PROFIT = 0.3            # 30% profit margin (StyleKorean)

VALID_STORES = {"style_korean", "yes_style"}


class CalculationError(ValueError):
    pass


def calculate_total(
    store: str,
    price: float,
    weight: float,
    time_deal: Optional[bool] = None,
    eligible_for_code: Optional[bool] = None,
) -> float:
    """
    Returns the final total in EGP, rounded to 2 decimal places.

    store:             "style_korean" or "yes_style"
    price:             product price in USD
    weight:            product weight in grams
    time_deal:         StyleKorean only — True if the "Time Deal" price applies
    eligible_for_code: YesStyle only — True if a discount code applies
    """
    if store not in VALID_STORES:
        raise CalculationError(f"Unknown store: {store!r}")
    if price is None or price <= 0:
        raise CalculationError("price must be a positive number")
    if weight is None or weight <= 0:
        raise CalculationError("weight must be a positive number")

    shipping = (weight / 1000) * SHIPPING_PER_KG

    if store == "style_korean":
        # Time Deal -> full price · Non Time Deal -> discounted
        service_fee = price * DOLLAR_RATE if time_deal else (price - DISCOUNT * price) * DOLLAR_RATE
        total = service_fee + (0.03 * service_fee) + (0.07 * (service_fee * 0.03 + service_fee)) + shipping
        total_with_profit = total + PROFIT * total
    else:
        # yes_style always uses the full-price service fee
        service_fee = price * DOLLAR_RATE
        total = service_fee + (0.03 * service_fee) + shipping
        total_with_profit = total + (0.2 * total) if eligible_for_code else total + (0.3 * total)

    return round(total_with_profit, 2)