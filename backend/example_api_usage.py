"""Example: Using Code Context in API Request"""
import requests
import json

# Sample code file content
order_model = '''
from enum import Enum
from pydantic import BaseModel, Field

class OrderStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class PaymentMethod(Enum):
    CREDIT_CARD = "credit_card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"

class Order(BaseModel):
    order_id: str
    product_id: str
    quantity: int = Field(ge=1, le=100)
    status: str
    payment_method: str
    email: str = Field(regex=r"^[^@]+@[^@]+\\\\.[^@]+$")
    
    def cancel(self):
        if self.status in ["shipped", "delivered"]:
            raise ValueError("Cannot cancel shipped or delivered orders")
        self.status = "cancelled"
'''

# Requirements
requirements = """
POST /orders (requires user_auth)
GET /orders/:id (requires user_auth, depends on POST /orders)
PUT /orders/:id/cancel (requires user_auth)
DELETE /orders/:id (requires user_auth)
"""

# API request with code context
request_payload = {
    "requirements_text": requirements,
    "existing_test_names": [],
    "output_formats": ["pytest"],
    "code_files": {
        "models/order.py": order_model
    },
    "code_language": "python"
}

# Make request (assuming server is running on localhost:8000)
def make_request():
    try:
        response = requests.post(
            "http://localhost:8000/generate-tests",
            json=request_payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            
            print("✅ Test generation successful!")
            print(f"\\n📊 Summary:")
            print(f"  • Endpoints: {len(result['context']['endpoints'])}")
            print(f"  • Test scenarios: {len(result['test_plan']['scenarios'])}")
            
            if result['context'].get('code_context'):
                cc = result['context']['code_context']
                print(f"\\n🔍 Code Context Extracted:")
                print(f"  • Enums: {len(cc.get('enums', []))}")
                print(f"  • Validators: {len(cc.get('validators', []))}")
                print(f"  • Business rules: {len(cc.get('business_rules', []))}")
                print(f"  • Models: {len(cc.get('models', []))}")
            
            print(f"\\n📝 Generated Code Preview:")
            print("-" * 60)
            code = result['generated_code']
            # Show first 20 lines
            lines = code.split('\\n')[:20]
            print('\\n'.join(lines))
            if len(code.split('\\n')) > 20:
                print("... (truncated)")
            
        else:
            print(f"❌ Request failed: {response.status_code}")
            print(f"Error: {response.json()}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Is it running?")
        print("Start with: cd backend && uvicorn main:app --reload")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("=" * 70)
    print("Code Context API Example")
    print("=" * 70)
    print("\\nMaking request to /generate-tests with code files...")
    print()
    make_request()
