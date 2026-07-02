import requests
r = requests.get('http://127.0.0.1:8000/leave/my/', allow_redirects=False)
print(r.status_code, r.headers.get('Location'))
