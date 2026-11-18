"""Download a workbook from a share link (OneDrive, SharePoint, Google Sheets, Dropbox or a direct link).

The link must be shared as "anyone with the link can view". Only public https
addresses are fetched (no addresses inside the server's own network).
"""
from __future__ import annotations

import base64
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from fastapi import HTTPException

MAX_BYTES = 20 * 1024 * 1024
NOT_SHARED = ("The link didn't give back an Excel file. Make sure it's shared as \"Anyone with the link can view\", "
              "or download the file and upload it instead.")


def download_url(link: str) -> str:
    """Turn a share link into one that returns the file itself."""
    link = link.strip()
    u = urlparse(link)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host:
        raise HTTPException(422, "Please paste a full https:// link")
    if host == "docs.google.com":
        m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", u.path)
        if not m:
            raise HTTPException(422, "This Google link isn't a spreadsheet")
        return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=xlsx"
    if host == "drive.google.com":
        m = re.search(r"/file/d/([A-Za-z0-9_-]+)", u.path) or re.search(r"[?&]id=([A-Za-z0-9_-]+)", link)
        if m:
            return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    if host in ("1drv.ms", "onedrive.live.com") or host.endswith(".onedrive.live.com"):
        # OneDrive's documented way to open a sharing link: base64url of the link, prefixed with u!
        token = base64.urlsafe_b64encode(link.encode()).decode().rstrip("=")
        return f"https://api.onedrive.com/v1.0/shares/u!{token}/root/content"
    if host.endswith(".sharepoint.com"):
        q = dict(parse_qsl(u.query))
        q["download"] = "1"
        return urlunparse(u._replace(query=urlencode(q)))
    if host.endswith("dropbox.com"):
        q = dict(parse_qsl(u.query))
        q["dl"] = "1"
        return urlunparse(u._replace(query=urlencode(q)))
    return link


def _check_public(url: str) -> None:
    host = urlparse(url).hostname or ""
    try:
        addrs = {i[4][0] for i in socket.getaddrinfo(host, 443)}
    except socket.gaierror:
        raise HTTPException(422, "That link's website couldn't be found")
    for a in addrs:
        ip = ipaddress.ip_address(a)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(422, "That link points inside a private network")


def fetch_workbook(link: str) -> tuple[bytes, str]:
    """Returns (file bytes, a name for the import log)."""
    url = download_url(link)
    with httpx.Client(timeout=60, follow_redirects=False, headers={"User-Agent": "HAYAH-AI/1.0"}) as c:
        for _ in range(8):  # follow redirects ourselves so each hop is checked
            _check_public(url)
            with c.stream("GET", url) as r:
                if r.is_redirect:
                    url = str(r.url.join(r.headers["location"]))
                    if urlparse(url).scheme != "https":
                        raise HTTPException(422, "The link redirected to an insecure address")
                    continue
                if r.status_code in (401, 403, 404):
                    raise HTTPException(422, NOT_SHARED)
                if r.status_code >= 400:
                    raise HTTPException(422, f"The link's website answered with an error ({r.status_code})")
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        raise HTTPException(413, "The file is larger than 20 MB")
                if not bytes(buf[:2]) == b"PK":  # .xlsx files are zip archives
                    raise HTTPException(422, NOT_SHARED)
                name = _name(r.headers.get("content-disposition")) or (urlparse(link).hostname or "link")
                return bytes(buf), name
    raise HTTPException(422, "The link redirected too many times")


def _name(disposition: str | None) -> str | None:
    if not disposition:
        return None
    m = re.search(r"filename\*=UTF-8''([^;]+)", disposition) or re.search(r'filename="?([^";]+)"?', disposition)
    if not m:
        return None
    from urllib.parse import unquote
    return unquote(m.group(1))[:120]
