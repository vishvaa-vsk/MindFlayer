"""
Enterprise Payment Processing Service
======================================
Scenario: E-commerce platform payment gateway integration
Features:
- Multi-currency support
- Fraud detection
- Refund management
- Payment status tracking
- Business validation rules
"""
from enum import Enum
from datetime import datetime
from decimal import Decimal
from typing import Optional


class PaymentStatus(Enum):
    """Payment lifecycle states."""
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    EXPIRED = "expired"


class Currency(Enum):
    """Supported currencies."""
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    INR = "INR"


class FraudRiskLevel(Enum):
    """Fraud detection risk levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PaymentValidationError(Exception):
    """Raised when payment validation fails."""
    pass


class InsufficientFundsError(Exception):
    """Raised when refund amount exceeds captured amount."""
    pass


class PaymentProcessor:
    """Enterprise payment processing engine."""
    
    # Business rules constants
    MIN_AMOUNT = Decimal("0.01")
    MAX_AMOUNT = Decimal("999999.99")
    FRAUD_THRESHOLD_USD = Decimal("10000.00")
    REFUND_WINDOW_DAYS = 90
    
    def __init__(self, merchant_id: str, api_key: str):
        """
        Initialize payment processor.
        
        Args:
            merchant_id: Unique merchant identifier
            api_key: API authentication key
        
        Raises:
            ValueError: If merchant_id or api_key is empty
        """
        if not merchant_id or not merchant_id.strip():
            raise ValueError("merchant_id cannot be empty")
        if not api_key or len(api_key) < 32:
            raise ValueError("api_key must be at least 32 characters")
        
        self.merchant_id = merchant_id.strip()
        self.api_key = api_key
        self._payment_db = {}  # Simulated database
    
    def create_payment(
        self,
        amount: Decimal,
        currency: Currency,
        customer_id: str,
        card_last4: str,
        card_type: str,
        customer_email: str,
        billing_country: str,
    ) -> dict:
        """
        Create a new payment transaction.
        
        Business Rules:
        1. Amount must be between MIN_AMOUNT and MAX_AMOUNT
        2. Customer email must be valid format
        3. Card last 4 digits must be exactly 4 characters
        4. Fraud check is triggered for amounts > FRAUD_THRESHOLD_USD
        5. Payments from high-risk countries require manual review
        
        Args:
            amount: Payment amount
            currency: Currency code
            customer_id: Customer identifier
            card_last4: Last 4 digits of card
            card_type: Card type (visa, mastercard, amex, etc.)
            customer_email: Customer email address
            billing_country: ISO country code
        
        Returns:
            dict: Payment record with transaction_id and status
        
        Raises:
            PaymentValidationError: If validation fails
        """
        # Validate amount
        if amount < self.MIN_AMOUNT:
            raise PaymentValidationError(
                f"Amount {amount} below minimum {self.MIN_AMOUNT}"
            )
        if amount > self.MAX_AMOUNT:
            raise PaymentValidationError(
                f"Amount {amount} exceeds maximum {self.MAX_AMOUNT}"
            )
        
        # Validate email format
        if "@" not in customer_email or "." not in customer_email:
            raise PaymentValidationError(f"Invalid email format: {customer_email}")
        
        # Validate card details
        if len(card_last4) != 4 or not card_last4.isdigit():
            raise PaymentValidationError("card_last4 must be exactly 4 digits")
        
        # Fraud risk assessment
        fraud_risk = self._assess_fraud_risk(
            amount, currency, billing_country, customer_id
        )
        
        # Auto-decline critical fraud risk
        if fraud_risk == FraudRiskLevel.CRITICAL:
            return {
                "transaction_id": self._generate_transaction_id(),
                "status": PaymentStatus.FAILED.value,
                "reason": "fraud_prevention",
                "fraud_risk": fraud_risk.value,
            }
        
        # Create payment record
        transaction_id = self._generate_transaction_id()
        status = (
            PaymentStatus.PENDING
            if fraud_risk == FraudRiskLevel.HIGH
            else PaymentStatus.AUTHORIZED
        )
        
        payment_record = {
            "transaction_id": transaction_id,
            "merchant_id": self.merchant_id,
            "amount": float(amount),
            "currency": currency.value,
            "customer_id": customer_id,
            "customer_email": customer_email,
            "card_last4": card_last4,
            "card_type": card_type,
            "billing_country": billing_country,
            "status": status.value,
            "fraud_risk": fraud_risk.value,
            "created_at": datetime.utcnow().isoformat(),
            "captured_amount": 0.0,
            "refunded_amount": 0.0,
        }
        
        self._payment_db[transaction_id] = payment_record
        return payment_record
    
    def capture_payment(self, transaction_id: str) -> dict:
        """
        Capture an authorized payment.
        
        Business Rules:
        1. Payment must exist and be in AUTHORIZED status
        2. Cannot capture PENDING, FAILED, or REFUNDED payments
        
        Args:
            transaction_id: Transaction identifier
        
        Returns:
            dict: Updated payment record
        
        Raises:
            ValueError: If transaction not found or not in correct status
        """
        if transaction_id not in self._payment_db:
            raise ValueError(f"Transaction {transaction_id} not found")
        
        payment = self._payment_db[transaction_id]
        
        if payment["status"] != PaymentStatus.AUTHORIZED.value:
            raise ValueError(
                f"Cannot capture payment with status {payment['status']}. "
                "Must be AUTHORIZED."
            )
        
        payment["status"] = PaymentStatus.CAPTURED.value
        payment["captured_amount"] = payment["amount"]
        payment["captured_at"] = datetime.utcnow().isoformat()
        
        return payment
    
    def refund_payment(
        self, transaction_id: str, refund_amount: Decimal, reason: str
    ) -> dict:
        """
        Refund a captured payment (full or partial).
        
        Business Rules:
        1. Payment must be CAPTURED or PARTIALLY_REFUNDED
        2. Refund amount cannot exceed remaining captured amount
        3. Cannot refund more than REFUND_WINDOW_DAYS after capture
        4. Refund reason is mandatory and must be non-empty
        
        Args:
            transaction_id: Transaction identifier
            refund_amount: Amount to refund
            reason: Reason for refund
        
        Returns:
            dict: Refund receipt with refund_id
        
        Raises:
            ValueError: If transaction not found or not captured
            InsufficientFundsError: If refund exceeds available amount
            PaymentValidationError: If outside refund window or invalid reason
        """
        if transaction_id not in self._payment_db:
            raise ValueError(f"Transaction {transaction_id} not found")
        
        payment = self._payment_db[transaction_id]
        
        # Check status
        if payment["status"] not in [
            PaymentStatus.CAPTURED.value,
            PaymentStatus.PARTIALLY_REFUNDED.value,
        ]:
            raise ValueError(
                f"Cannot refund payment with status {payment['status']}"
            )
        
        # Validate reason
        if not reason or not reason.strip():
            raise PaymentValidationError("Refund reason cannot be empty")
        
        # Check refund window
        captured_at = datetime.fromisoformat(payment["captured_at"])
        days_since_capture = (datetime.utcnow() - captured_at).days
        if days_since_capture > self.REFUND_WINDOW_DAYS:
            raise PaymentValidationError(
                f"Refund window of {self.REFUND_WINDOW_DAYS} days exceeded"
            )
        
        # Calculate available amount
        available_amount = Decimal(str(payment["captured_amount"])) - Decimal(
            str(payment["refunded_amount"])
        )
        
        if refund_amount > available_amount:
            raise InsufficientFundsError(
                f"Refund amount {refund_amount} exceeds available {available_amount}"
            )
        
        # Process refund
        payment["refunded_amount"] = float(
            Decimal(str(payment["refunded_amount"])) + refund_amount
        )
        
        if payment["refunded_amount"] >= payment["captured_amount"]:
            payment["status"] = PaymentStatus.REFUNDED.value
        else:
            payment["status"] = PaymentStatus.PARTIALLY_REFUNDED.value
        
        refund_id = f"refund_{self._generate_transaction_id()}"
        
        refund_receipt = {
            "refund_id": refund_id,
            "transaction_id": transaction_id,
            "refund_amount": float(refund_amount),
            "currency": payment["currency"],
            "reason": reason.strip(),
            "refunded_at": datetime.utcnow().isoformat(),
            "remaining_amount": float(available_amount - refund_amount),
        }
        
        return refund_receipt
    
    def get_payment_status(self, transaction_id: str) -> dict:
        """
        Retrieve current payment status.
        
        Args:
            transaction_id: Transaction identifier
        
        Returns:
            dict: Payment status information
        
        Raises:
            ValueError: If transaction not found
        """
        if transaction_id not in self._payment_db:
            raise ValueError(f"Transaction {transaction_id} not found")
        
        payment = self._payment_db[transaction_id]
        
        return {
            "transaction_id": transaction_id,
            "status": payment["status"],
            "amount": payment["amount"],
            "captured_amount": payment["captured_amount"],
            "refunded_amount": payment["refunded_amount"],
            "currency": payment["currency"],
            "fraud_risk": payment["fraud_risk"],
        }
    
    def _assess_fraud_risk(
        self, amount: Decimal, currency: Currency, country: str, customer_id: str
    ) -> FraudRiskLevel:
        """
        Assess fraud risk level based on transaction parameters.
        
        Business Rules:
        1. Amounts > FRAUD_THRESHOLD_USD are flagged HIGH
        2. High-risk countries (e.g., known for fraud) are flagged CRITICAL
        3. First-time customers with large amounts are flagged HIGH
        4. Otherwise LOW or MEDIUM
        """
        # High-risk countries (simplified example)
        HIGH_RISK_COUNTRIES = ["XX", "YY", "ZZ"]
        
        if country in HIGH_RISK_COUNTRIES:
            return FraudRiskLevel.CRITICAL
        
        # Convert to USD equivalent (simplified)
        amount_usd = self._convert_to_usd(amount, currency)
        
        if amount_usd > self.FRAUD_THRESHOLD_USD:
            return FraudRiskLevel.HIGH
        
        # Check if first-time customer (simplified)
        if customer_id.startswith("new_") and amount_usd > Decimal("1000.00"):
            return FraudRiskLevel.HIGH
        
        if amount_usd > Decimal("500.00"):
            return FraudRiskLevel.MEDIUM
        
        return FraudRiskLevel.LOW
    
    def _convert_to_usd(self, amount: Decimal, currency: Currency) -> Decimal:
        """Convert amount to USD for fraud assessment (simplified rates)."""
        rates = {
            Currency.USD: Decimal("1.0"),
            Currency.EUR: Decimal("1.1"),
            Currency.GBP: Decimal("1.3"),
            Currency.JPY: Decimal("0.0075"),
            Currency.INR: Decimal("0.012"),
        }
        return amount * rates.get(currency, Decimal("1.0"))
    
    def _generate_transaction_id(self) -> str:
        """Generate unique transaction ID."""
        import uuid
        return f"txn_{uuid.uuid4().hex[:16]}"
