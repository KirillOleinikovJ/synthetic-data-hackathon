from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _dec(value: object) -> object:
    if isinstance(value, float):
        return Decimal(str(value))
    return value


class Address(BaseModel):
    street: str
    postal_code: str
    city: str
    country: str = "DE"


class Patient(BaseModel):
    salutation: str  # e.g. Frau / Herr
    full_name: str
    birth_date: date
    address: Address
    patient_number: str
    insurance_number: str | None = None


class Provider(BaseModel):
    physician_name: str
    specialty: str
    address: Address
    tax_id: str | None = None
    lanr: str | None = None
    bsnr: str | None = None


class BankDetails(BaseModel):
    bank_name: str
    iban: str
    bic: str


class LineItem(BaseModel):
    """One GOÄ Leistungszeile."""

    service_date: date
    code: str  # GOÄ Nr.
    description: str
    quantity: Decimal = Field(gt=0)
    factor: Decimal = Field(gt=0, description="Steigerungssatz")
    einfachsatz_eur: Decimal = Field(ge=0)
    line_total_eur: Decimal = Field(ge=0)

    @field_validator(
        "quantity",
        "factor",
        "einfachsatz_eur",
        "line_total_eur",
        mode="before",
    )
    @classmethod
    def _to_decimal(cls, value: object) -> object:
        return _dec(value)


class MaterialItem(BaseModel):
    """Sachkosten / Auslagen §10 GOÄ."""

    description: str
    quantity: Decimal = Field(gt=0)
    unit_price_eur: Decimal = Field(ge=0)
    line_total_eur: Decimal = Field(ge=0)

    @field_validator("quantity", "unit_price_eur", "line_total_eur", mode="before")
    @classmethod
    def _to_decimal(cls, value: object) -> object:
        return _dec(value)


class InvoiceTotals(BaseModel):
    services_eur: Decimal = Field(ge=0)  # Summe ärztliche Leistung
    materials_eur: Decimal = Field(ge=0)  # Summe Sachkosten
    gross_eur: Decimal = Field(ge=0)  # Rechnungsbetrag gesamt
    tax_eur: Decimal = Field(default=Decimal("0.00"), ge=0)

    @field_validator("services_eur", "materials_eur", "gross_eur", "tax_eur", mode="before")
    @classmethod
    def _to_decimal(cls, value: object) -> object:
        return _dec(value)


class Invoice(BaseModel):
    """Synthetic German GOÄ medical invoice — single source for JSON + PDF."""

    schema_version: Literal["1.1"] = "1.1"
    scenario_id: str
    billing_rule: str = "Gebuehrenordnung fuer Aerzte / GOAE (Stand 01.01.2002)"
    invoice_number: str
    patient_number: str
    issue_date: date
    service_until: date
    payment_due_date: date
    currency: Literal["EUR"] = "EUR"
    diagnosis: str
    patient: Patient
    provider: Provider
    bank: BankDetails
    service_period_start: date
    service_period_end: date
    line_items: list[LineItem] = Field(min_length=1)
    materials: list[MaterialItem] = Field(default_factory=list)
    totals: InvoiceTotals
    notes: str | None = None
