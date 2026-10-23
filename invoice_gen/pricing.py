"""GOÄ money math. The model never supplies these amounts.

Sources
-------
- Point counts: GOÄ Anlage, https://www.gesetze-im-internet.de/go__1982/anlage.html
- Factor limits: GOÄ § 5, https://www.gesetze-im-internet.de/go__1982/__5.html
  Personal medical services: 1.0–3.5, threshold 2.3 without a written justification.
  Zuschläge 440–449: simple rate only (Anlage, section C.VIII).
- Point value: the Anlage prices one point at 0.114 DM (80 points = 9.12 DM).
  The statutory euro rate is 1 EUR = 1.95583 DM, so
  0.114 / 1.95583 = 0.0582873 EUR. The Bundesärztekammer publishes this as
  5.82873 cent.

Rounding order used here
------------------------
1. Einfachsatz = round half up (points × 0.0582873) to the cent.
2. Line amount = round half up (Einfachsatz × factor × quantity) to the cent.

Ziffer 34 in the Allianz sample invoices is 40.23 EUR at factor 2.3.
That matches step 1 then step 2 (17.49 × 2.3 = 40.227 → 40.23).
Multiplying points × point value × factor in one step gives 40.22 and does
not match those invoices. This is the calculation used by the program, not
a court ruling on every billing dispute.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

PUNKTWERT_EUR = Decimal("0.0582873")
MONEY = Decimal("0.01")
CENT = Decimal("0.01")


def round_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def einfachsatz_from_points(points: int) -> Decimal:
    return round_money(Decimal(points) * PUNKTWERT_EUR)


def line_amount(einfachsatz: Decimal, factor: Decimal, quantity: Decimal) -> Decimal:
    return round_money(einfachsatz * factor * quantity)
