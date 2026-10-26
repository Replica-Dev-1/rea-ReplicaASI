"""chain - READ-ONLY Solana helpers for REPLICA. The server never holds a key and never sends a transaction of its
own: hosts mint from their own wallets (the page relays only blockhash/send/status through /api/rpc); this module reads.

A replica is a Metaplex Core asset (AssetV1, borsh):
  key u8 (1 = AssetV1) | owner [32] | update_authority enum (u8 tag: 0 None, 1 Address+[32], 2 Collection+[32])
  | name string (u32 len + utf8) | uri string | seq Option<u64>
The coin that gates waking is an SPL token (config gate_token = its mint).
"""
from __future__ import annotations

import base64
import json
import re
import struct
import time
import urllib.request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

CORE_PROGRAM = "CoREENxT6tW1HoK8ypY1SxRMZTcVPm7R94rH4PZNhX7d"
MAINNET_GENESIS = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ADDR_RX = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_cache: dict[tuple, tuple[float, object]] = {}


def b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + out


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw


def norm(addr: str) -> str:
    """a Solana address (base58, 32 bytes) as given, or "" if it isn't one. Case matters on Solana."""
    addr = (addr or "").strip()
    try:
        return addr if ADDR_RX.match(addr) and len(b58decode(addr)) == 32 else ""
    except ValueError:
        return ""


def signed_by(message: str, signature_b64: str, wallet: str) -> bool:
    """did `wallet` sign `message` (wallet signMessage, ed25519 over the utf-8 bytes)?"""
    try:
        Ed25519PublicKey.from_public_bytes(b58decode(wallet)).verify(base64.b64decode(signature_b64), message.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError):
        return False


def rpc(url: str, method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "replica/1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode("utf-8"))
    if "error" in d:
        raise RuntimeError(d["error"].get("message", "rpc error"))
    return d["result"]


def _string(b: bytes, i: int) -> tuple[str, int]:
    (n,) = struct.unpack_from("<I", b, i)
    if n > 2000:
        raise ValueError("string too long")
    return b[i + 4:i + 4 + n].decode("utf-8"), i + 4 + n


def parse_core_asset(data: bytes) -> dict:
    if not data or data[0] != 1:
        raise ValueError("not a Core AssetV1 account")
    owner = b58encode(data[1:33])
    tag, i = data[33], 34
    ua = None
    if tag in (1, 2):
        ua, i = b58encode(data[i:i + 32]), i + 32
    elif tag != 0:
        raise ValueError("bad update authority")
    name, i = _string(data, i)
    uri, i = _string(data, i)
    return {"owner": owner, "update_authority": ua, "name": name, "uri": uri}


def core_asset(url: str, asset: str, ttl: float = 20.0) -> dict | None:
    """current on-chain state of a Core asset (owner, name, uri); None if it does not exist. Cached `ttl` seconds."""
    key = ("asset", url, asset)
    hit = _cache.get(key)
    if hit and ttl and time.time() - hit[0] < ttl:
        return hit[1]
    res = rpc(url, "getAccountInfo", [asset, {"encoding": "base64", "commitment": "confirmed"}])
    v = res.get("value")
    out = None
    if v and v.get("owner") == CORE_PROGRAM:
        out = parse_core_asset(base64.b64decode(v["data"][0]))
    _cache[key] = (time.time(), out)
    return out


def owner_of(url: str, asset: str, ttl: float = 20.0) -> str | None:
    st = core_asset(url, asset, ttl)
    return st["owner"] if st else None


def token_balance(url: str, wallet: str, mint: str) -> float:
    """how much of SPL token `mint` the wallet holds, over all its token accounts (classic SPL and Token-2022)"""
    total = 0.0
    for program in ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
        res = rpc(url, "getTokenAccountsByOwner",
                  [wallet, {"programId": program}, {"encoding": "jsonParsed", "commitment": "confirmed"}])
        for acc in res["value"]:
            info = acc["account"]["data"]["parsed"]["info"]
            if info.get("mint") == mint:
                amt = info["tokenAmount"]
                total += float(amt.get("uiAmountString") or amt.get("uiAmount") or 0)
    return total
