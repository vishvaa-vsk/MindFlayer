"""
FastAPI wrapper for PaymentProcessor - USE THIS for test generation
"""
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from decimal import Decimal
from test_enterprise_payment_service import (
    PaymentProcessor, Currency, PaymentStatus,
    PaymentValidationError, InsufficientFundsError
)

app = FastAPI()

# In production, use proper dependency injection
processor = PaymentProcessor(
    merchant_id="merchant_001",
    api_key="production_api_key_32_chars_min"
)


class CreatePaymentRequest(BaseModel):
    amount: float
    currency: str
    customer_id: str
    card_last4: str
    card_type: str
    customer_email: str
    billing_country: str


class RefundRequest(BaseModel):
    amount: float
    reason: str


@app.post("/payments")
def create_payment(req: CreatePaymentRequest):
    """Create a new payment."""
    try:
        result = processor.create_payment(
            amount=Decimal(str(req.amount)),
            currency=Currency[req.currency],
            customer_id=req.customer_id,
            card_last4=req.card_last4,
            card_type=req.card_type,
            customer_email=req.customer_email,
            billing_country=req.billing_country
        )
        return result
    except PaymentValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/payments/{transaction_id}/capture")
def capture_payment(transaction_id: str):
    """Capture an authorized payment."""
    try:
        result = processor.capture_payment(transaction_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/payments/{transaction_id}/refund")
def refund_payment(transaction_id: str, req: RefundRequest):
    """Refund a captured payment."""
    try:
        result = processor.refund_payment(
            transaction_id=transaction_id,
            refund_amount=Decimal(str(req.amount)),
            reason=req.reason
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientFundsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PaymentValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/payments/{transaction_id}")
def get_payment_status(transaction_id: str):
    """Get payment status."""
    try:
        result = processor.get_payment_status(transaction_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
