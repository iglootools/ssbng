"""DNS resolution and network classification helpers."""

from __future__ import annotations

import ipaddress
import socket


def resolve_host(hostname: str) -> set[str] | None:
    """Resolve hostname to IP addresses.

    Returns ``None`` if the hostname cannot be resolved.
    """
    try:
        results = socket.getaddrinfo(hostname, None)
        return {str(r[4][0]) for r in results}
    except socket.gaierror:
        return None


def is_private_host(hostname: str) -> bool | None:
    """Check whether *hostname* resolves to private addresses.

    Returns ``True`` if all resolved addresses are private,
    ``False`` if any is public, or ``None`` if the hostname
    cannot be resolved.
    """
    addrs = resolve_host(hostname)
    if addrs is None:
        return None
    return all(ipaddress.ip_address(a).is_private for a in addrs)
