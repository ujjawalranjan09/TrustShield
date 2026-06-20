import sys
sys.path.insert(0, 'backend')

import os
os.environ['DATABASE_URL'] = 'sqlite:///./trustshield.db'

# Now import the app
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=True)

# Test login
resp = client.post('/api/v1/auth/login', json={
    'email': 'testlive999@example.com',
    'password': 'TestPass123!'
})
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text}')
