import requests
import json

payload = {
    'supplier_name': 'Test Supplier',
    'item_name': 'milk',
    'quantity': '5',
    'total_amount': '100',
    'paid_amount': '50',
    'transaction_date': '2026-04-18'
}

r = requests.post('http://127.0.0.1:5000/transactions', json=payload)
print('Status:', r.status_code)
print('Content-Type:', r.headers.get('content-type'))
print('Raw Response Text:')
print(r.text)
if r.status_code == 200:
    print('Parsed JSON:')
    print(json.dumps(r.json(), indent=2))
