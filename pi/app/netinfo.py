from __future__ import annotations

import secrets
import socket
from functools import lru_cache


def local_ipv4_addresses() -> frozenset[str]:
    """IPv4 addresses on this host that stations may use as the API key."""
    found: set[str] = {"127.0.0.1"}
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addr = info[4][0]
            if addr:
                found.add(addr)
    except OSError:
        pass

    # UDP "connect" trick — discovers the primary outbound/LAN interface IP
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            addr = probe.getsockname()[0]
            if addr:
                found.add(addr)
        finally:
            probe.close()
    except OSError:
        pass

    # Drop link-local noise unless that's all we have
    non_link = {a for a in found if not a.startswith("169.254.")}
    return frozenset(non_link or found)


@lru_cache
def primary_ipv4() -> str:
    """Best guess at the LAN IP staff should put in station config."""
    addrs = local_ipv4_addresses()
    preferred = sorted(
        (a for a in addrs if a != "127.0.0.1" and not a.startswith("169.254.")),
        key=lambda a: (a.startswith("172."), a.startswith("10."), a),
    )
    if preferred:
        return preferred[0]
    return "127.0.0.1"


def is_valid_api_key(token: str) -> bool:
    """API key is literally one of this machine's IPv4 addresses."""
    if not token:
        return False
    for addr in local_ipv4_addresses():
        # compare_digest requires equal length; pad-safe: only compare equals-length
        if len(token) == len(addr) and secrets.compare_digest(token, addr):
            return True
    return False
