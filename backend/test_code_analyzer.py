"""Test script for code analyzer functionality."""
import sys
sys.path.insert(0, '/home/vishvaa/projects/MindFlayer/backend')

from context.code_analyzer import analyze_python_file

# Sample Python code with enums, validators, and business rules
sample_code = '''
from enum import Enum
from pydantic import BaseModel, Field, validator

class OrderStatus(Enum):
    """Order status values."""
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentMethod(Enum):
    """Payment methods."""
    CREDIT_CARD = "credit_card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"


class Order(BaseModel):
    """Order model with validation."""
    order_id: str
    product_id: str
    quantity: int = Field(ge=1, le=100)
    status: str
    payment_method: str
    email: str = Field(regex=r"^[^@]+@[^@]+\\.[^@]+$")
    
    @validator("quantity")
    def validate_quantity(cls, v):
        if v < 1:
            raise ValueError("Quantity must be at least 1")
        if v > 100:
            raise ValueError("Quantity cannot exceed 100")
        return v
    
    def cancel(self):
        """Cancel an order if possible."""
        if self.status in ["shipped", "delivered"]:
            raise ValueError("Cannot cancel orders that have been shipped or delivered")
        self.status = "cancelled"
    
    def ship(self):
        """Ship an order."""
        if self.status != "processing":
            raise ValueError("Can only ship orders that are being processed")
        self.status = "shipped"
'''

def test_code_analyzer():
    """Test the code analyzer with sample code."""
    print("=" * 60)
    print("Testing Code Analyzer")
    print("=" * 60)
    
    try:
        code_context = analyze_python_file(sample_code, "sample_order.py")
        
        print(f"\\n✅ Analysis completed successfully!")
        print(f"\\n📊 Results:")
        print(f"  • Enums found: {len(code_context.enums)}")
        for enum in code_context.enums:
            print(f"    - {enum.name}: {enum.values}")
        
        print(f"\\n  • Models found: {len(code_context.models)}")
        for model in code_context.models:
            print(f"    - {model.name} ({len(model.fields)} fields)")
        
        print(f"\\n  • Validators found: {len(code_context.validators)}")
        for validator in code_context.validators:
            print(f"    - {validator.field_name}: {validator.rule_type} = {validator.constraint}")
        
        print(f"\\n  • Business rules found: {len(code_context.business_rules)}")
        for rule in code_context.business_rules:
            print(f"    - {rule.applies_to}: {rule.condition[:50]}...")
        
        print(f"\\n✅ All extractions successful!")
        
        # Test enum lookup
        print(f"\\n🔍 Testing enum lookup:")
        status_values = code_context.get_enum_values("OrderStatus")
        print(f"  OrderStatus values: {status_values}")
        
        # Test validator lookup
        print(f"\\n🔍 Testing validator lookup:")
        quantity_validators = code_context.get_validators_for_field("quantity")
        print(f"  Quantity validators: {len(quantity_validators)}")
        
        return True
        
    except Exception as e:
        print(f"\\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_code_analyzer()
    sys.exit(0 if success else 1)
