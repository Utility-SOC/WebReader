"""
SSRF-resistant HTTP fetching for /fetch_url.

A server that fetches user-supplied URLs can be aimed at things only it can
reach: cloud metadata services (169.254.169.254), other containers (redis,
the backend itself), anything on a private network. Two things make a
hostname check alone insufficient: DNS can answer differently the second time
(rebinding), and every redirect is a new destination.

So for every connection -- including each redirect hop -- we resolve the
name ourselves, refuse if ANY answer is not a globally routable address, and
then connect to the exact IP we vetted (so a second DNS lookup can't change
the answer). A blocked target is never contacted at all, which also denies an
attacker the open/closed-port timing signal a connect-then-check design leaks.

  - Allowed: globally routable addresses only (no loopback, private,
    link-local, CGN, multicast, reserved, unspecified).
  - Environment proxies are ignored (trust_env=False); a proxy would hide the
    real destination from this check.
  - Redirects are capped, and connect/read timeouts are set.
  - Escape hatch for a desktop user who really wants intranet URLs:
    WEBREADER_FETCH_ALLOW_PRIVATE=1.
"""

import ipaddress
import os
import socket

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.util.connection import create_connection

MAX_REDIRECTS = 5
DEFAULT_TIMEOUT = (5, 30)  # connect, read (seconds)


class BlockedAddressError(requests.exceptions.ConnectionError):
    """The URL resolves to an address this server must not connect to."""


def allow_private() -> bool:
    return os.environ.get("WEBREADER_FETCH_ALLOW_PRIVATE", "").strip() == "1"


def is_public_address(addr: str) -> bool:
    ip = ipaddress.ip_address(addr.split("%")[0])  # drop IPv6 zone id
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not (ip.is_multicast or ip.is_unspecified)


def _connect_vetted(conn):
    """Resolve conn's host, vet every answer, connect to a vetted IP."""
    host = getattr(conn, "_dns_host", conn.host)
    infos = socket.getaddrinfo(host, conn.port, type=socket.SOCK_STREAM)
    addrs = [info[4][0] for info in infos]
    if not allow_private():
        bad = [a for a in addrs if not is_public_address(a)]
        if bad:
            raise BlockedAddressError(f"Refusing to connect to non-public address {bad[0]}")
    last_err = OSError(f"could not resolve {host}")
    for addr in addrs:
        try:
            return create_connection((addr, conn.port), conn.timeout, conn.source_address, conn.socket_options)
        except OSError as e:
            last_err = e
    raise last_err


class _SafeHTTPConnection(HTTPConnection):
    def _new_conn(self):
        return _connect_vetted(self)


class _SafeHTTPSConnection(HTTPSConnection):
    def _new_conn(self):
        return _connect_vetted(self)


class _SafeHTTPPool(HTTPConnectionPool):
    ConnectionCls = _SafeHTTPConnection


class _SafeHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _SafeHTTPSConnection


class _SafeAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {"http": _SafeHTTPPool, "https": _SafeHTTPSPool}


def safe_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    s.max_redirects = MAX_REDIRECTS
    adapter = _SafeAdapter()
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def safe_get(url: str, timeout=DEFAULT_TIMEOUT) -> requests.Response:
    """GET `url` as a stream. Raises BlockedAddressError for non-public targets."""
    try:
        return safe_session().get(url, stream=True, timeout=timeout)
    except requests.exceptions.ConnectionError as e:
        if "non-public address" in str(e):
            raise BlockedAddressError(str(e)) from None
        raise
