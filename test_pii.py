import requests
import json

# Test explain PII redaction
r = requests.post('http://localhost:8000/api/v1/explain', json={'text': 'My Aadhaar is 1234-5678-9012'})
print(f'Explain: {r.status_code}')
print(f'Response: {r.text}')
print(f'Aadhaar leaked: {"1234-5678-9012" in r.text}')
