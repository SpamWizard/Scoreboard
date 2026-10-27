from __future__ import annotations

from fastapi import Header, HTTPException, status

from .netinfo import is_valid_api_key, primary_ipv4


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """Stations authenticate with the Pi's IP address as the bearer token."""
    token = _extract_bearer(authorization)
    if not token or not is_valid_api_key(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Invalid or missing bearer token "
                f"(use the Pi IP address, e.g. Bearer {primary_ipv4()})"
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_admin_token(authorization: str | None = Header(default=None)) -> None:
    """Same key as runs: the Pi IP address."""
    require_api_token(authorization)
