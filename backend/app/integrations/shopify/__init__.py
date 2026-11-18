"""Official Shopify Admin API client for HAYAH's own store.

Two ways to sign in, both official:
- A Dev Dashboard app installed on the store: client ID + client secret are
  exchanged for a 24-hour token (client credentials grant), refreshed here.
- An older custom app made in the Shopify admin: its Admin API access token
  (shpat_...) is used directly.

Webhooks are verified with the app's client secret (X-Shopify-Hmac-Sha256).
Nothing here is ever sent to the browser.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time

import httpx

API_VERSION = "2026-10"
_transport: httpx.BaseTransport | None = None  # tests swap in httpx.MockTransport


class ShopifyError(Exception):
    pass


def set_transport(t: httpx.BaseTransport | None) -> None:
    global _transport
    _transport = t


def normalize_domain(value: str | None) -> str:
    """Accept 'abc.myshopify.com', 'https://abc.myshopify.com/admin', 'admin.shopify.com/store/abc' or 'abc'."""
    v = (value or "").strip().lower()
    if not v:
        return ""
    m = re.search(r"admin\.shopify\.com/store/([a-z0-9][a-z0-9-]*)", v)
    if m:
        return f"{m.group(1)}.myshopify.com"
    v = re.sub(r"^https?://", "", v).split("/")[0]
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*", v):
        return f"{v}.myshopify.com"
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", v):
        return v
    raise ShopifyError("Use the store's .myshopify.com address (Shopify admin > Settings > Domains), not the public website address")


def verify_hmac(body: bytes, header: str | None, secret: str) -> bool:
    if not header or not secret:
        return False
    digest = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(digest, header.strip())


def _client() -> httpx.Client:
    return httpx.Client(timeout=30, transport=_transport) if _transport else httpx.Client(timeout=30)


def client_credentials_token(domain: str, client_id: str, client_secret: str) -> tuple[str, float]:
    with _client() as c:
        r = c.post(f"https://{domain}/admin/oauth/access_token",
                   data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret})
    if r.status_code != 200:
        raise ShopifyError(f"Shopify refused the app keys ({r.status_code}): {r.text[:200]}. "
                           "Check the client ID/secret and that the app is installed on this store.")
    j = r.json()
    return j["access_token"], time.time() + float(j.get("expires_in", 86399)) - 300


def graphql(domain: str, token: str, query: str, variables: dict | None = None, version: str = API_VERSION) -> dict:
    with _client() as c:
        r = c.post(f"https://{domain}/admin/api/{version}/graphql.json",
                   headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                   json={"query": query, "variables": variables or {}})
    if r.status_code == 401:
        raise ShopifyError("Shopify says the access token is not valid (401)")
    if r.status_code == 403:
        raise ShopifyError("The Shopify app is missing a permission (403). It needs read_orders.")
    if r.status_code >= 400:
        raise ShopifyError(f"Shopify error {r.status_code}: {r.text[:300]}")
    j = r.json()
    if j.get("errors"):
        raise ShopifyError(f"Shopify error: {str(j['errors'])[:400]}")
    return j.get("data") or {}


def gid_number(gid) -> int:
    """'gid://shopify/Order/123' -> 123 (also accepts plain numbers)."""
    return int(str(gid).rsplit("/", 1)[-1])
