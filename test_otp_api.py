import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from api.models import OTPToken
from api.views import AuthView, hash_otp

def run_tests():
    print("--- STARTING OTP API VERIFICATION TESTS ---")
    factory = RequestFactory()
    view = AuthView.as_view()
    test_email = "testuser_otp@example.com"

    # Clean up previous test records
    OTPToken.objects.filter(email=test_email).delete()
    User.objects.filter(email=test_email).delete()

    # TEST 1: Send OTP
    print("\n1. Testing Send OTP endpoint...")
    request = factory.post('/api/auth/send-otp', {'email': test_email}, content_type='application/json')
    response = view(request, action='send-otp')
    print(f"Status Code: {response.status_code}")
    print(f"Response Data: {response.data}")
    assert response.status_code == 200, "Send OTP failed"

    # Retrieve created token
    otp_record = OTPToken.objects.filter(email=test_email, is_used=False).latest('created_at')
    print(f"OTP Token created in DB. Expiring at: {otp_record.expires_at}")

    # TEST 2: Rate limiting (Immediate second request should return 429)
    print("\n2. Testing 60s Cooldown / Rate Limiting...")
    request2 = factory.post('/api/auth/send-otp', {'email': test_email}, content_type='application/json')
    response2 = view(request2, action='send-otp')
    print(f"Status Code: {response2.status_code}")
    print(f"Response Data: {response2.data}")
    assert response2.status_code == 429, "Rate limiting failed to block spam"

    # TEST 3: Verify with Wrong Code
    print("\n3. Testing Invalid OTP Code verification...")
    request3 = factory.post('/api/auth/verify-otp', {'email': test_email, 'otp': '000000'}, content_type='application/json')
    response3 = view(request3, action='verify-otp')
    print(f"Status Code: {response3.status_code}")
    print(f"Response Data: {response3.data}")
    assert response3.status_code == 400, "Should reject invalid OTP"

    # TEST 4: Verify with Correct Code
    # For testing, we verify with an OTP code that matches the hash
    correct_otp = "123456"
    otp_record.otp_hash = hash_otp(correct_otp)
    otp_record.save()

    print("\n4. Testing Valid OTP Code verification...")
    request4 = factory.post('/api/auth/verify-otp', {'email': test_email, 'otp': correct_otp}, content_type='application/json')
    response4 = view(request4, action='verify-otp')
    print(f"Status Code: {response4.status_code}")
    print(f"Response Data: {response4.data}")
    assert response4.status_code == 200, "Valid OTP verification failed"
    assert 'token' in response4.data, "Token missing in response"
    assert response4.data['user']['email'] == test_email, "User email mismatch"

    print("\n--- ALL OTP TESTS PASSED SUCCESSFULLY! ---")

if __name__ == '__main__':
    run_tests()
