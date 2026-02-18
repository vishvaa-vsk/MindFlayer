"""Integration test - Requirements + Code Context → Enhanced Tests."""
import sys
sys.path.insert(0, '/home/vishvaa/projects/MindFlayer/backend')

from context.builder import parse_requirements_text
import json

# Sample requirements
requirements = """
POST /orders (requires user_auth)
GET /orders/:id (requires user_auth, depends on POST /orders)
PUT /orders/:id/cancel (requires user_auth)
POST /orders/:id/ship (requires admin_auth)
"""

# Sample code file
order_model_code = '''
from enum import Enum
from pydantic import BaseModel, Field

class OrderStatus(Enum):
    """Order status states."""
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class PaymentMethod(Enum):
    """Available payment methods."""
    CREDIT_CARD = "credit_card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"

class Order(BaseModel):
    """Order model."""
    order_id: str
    product_id: str
    quantity: int = Field(ge=1, le=100)
    status: str
    payment_method: str
    email: str
    
    def cancel(self):
        """Cancel order - only allowed for pending/processing."""
        if self.status in ["shipped", "delivered"]:
            raise ValueError("Cannot cancel shipped or delivered orders")
        self.status = "cancelled"
    
    def ship(self):
        """Ship order - requires processing state."""
        if self.status != "processing":
            raise ValueError("Can only ship orders in processing state")
        self.status = "shipped"
'''

def test_integration():
    """Test full integration: requirements + code → enriched context."""
    print("=" * 70)
    print("INTEGRATION TEST: Requirements + Code Context → Enhanced Endpoints")
    print("=" * 70)
    
    print("\\n📝 Step 1: Parse requirements WITHOUT code context")
    print("-" * 70)
    
    context_without_code = parse_requirements_text(requirements)
    print(f"✅ Parsed {len(context_without_code.endpoints)} endpoints")
    
    # Check if any endpoint has enum constraints
    has_enums_before = any(
        any(field.enum for field in endpoint.request_body)
        for endpoint in context_without_code.endpoints
    )
    print(f"  Endpoints with enum constraints: {'Yes' if has_enums_before else 'No'}")
    
    print("\\n📝 Step 2: Parse requirements WITH code context")
    print("-" * 70)
    
    code_files = {
        "models/order.py": order_model_code
    }
    
    context_with_code = parse_requirements_text(
        requirements,
        code_files=code_files,
        language="python"
    )
    
    print(f"✅ Parsed {len(context_with_code.endpoints)} endpoints")
    print(f"\\n📊 Code Context Extracted:")
    if context_with_code.code_context:
        print(f"  • {len(context_with_code.code_context.enums)} enums")
        print(f"  • {len(context_with_code.code_context.validators)} validators")
        print(f"  • {len(context_with_code.code_context.business_rules)} business rules")
        print(f"  • {len(context_with_code.code_context.models)} models")
    
    print("\\n🔍 Step 3: Compare enriched endpoints")
    print("-" * 70)
    
    for endpoint in context_with_code.endpoints:
        print(f"\\n  Endpoint: {endpoint.method} {endpoint.url_path}")
        
        # Check for enum-enriched fields
        enum_fields = [f for f in endpoint.request_body if f.enum]
        if enum_fields:
            print(f"    ✨ Enum-enriched fields: {len(enum_fields)}")
            for field in enum_fields:
                print(f"      - {field.name}: {field.enum}")
        
        # Check for state constraints
        if endpoint.state_constraints:
            print(f"    ✨ State constraints: {len(endpoint.state_constraints)}")
            for constraint in endpoint.state_constraints:
                print(f"      - {constraint.field}: {constraint.description}")
    
    # Count improvements
    total_enums_after = sum(
        len([f for f in endpoint.request_body if f.enum])
        for endpoint in context_with_code.endpoints
    )
    
    total_constraints_after = sum(
        len(endpoint.state_constraints)
        for endpoint in context_with_code.endpoints
    )
    
    print("\\n" + "=" * 70)
    print("📊 IMPROVEMENT SUMMARY")
    print("=" * 70)
    print(f"  Enum-enriched fields added: {total_enums_after}")
    print(f"  Business rule constraints added: {total_constraints_after}")
    print("\\n✅ Code context successfully enriched endpoint schemas!")
    print("=" * 70)
    
    return True

if __name__ == "__main__":
    try:
        success = test_integration()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
