"""Minimal Albert Heijn mobile-API client used by the collector."""
import json
import urllib.request

API = "https://api.ah.nl"
HEADERS = {"User-Agent": "Appie/8.22.3", "X-Application": "AHWEBSHOP"}


def _call(path, token=None, method="GET", body=None):
    req = urllib.request.Request(API + path, method=method)
    for k, v in HEADERS.items():
        req.add_header(k, v)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def anonymous_token():
    return _call("/mobile-auth/v1/auth/token/anonymous", method="POST",
                 body={"clientId": "appie"})["access_token"]


def product_detail(token, webshop_id):
    d = _call(f"/mobile-services/product/detail/v4/fir/{webshop_id}", token)
    return d.get("productCard", d)
