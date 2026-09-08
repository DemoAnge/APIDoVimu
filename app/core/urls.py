from urllib.parse import urlparse

from app.core.exceptions import InvalidUrlError

_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
}

_BLOCKED_PREFIXES = (
    "127.",
    "10.",
    "192.168.",
    "169.254.",
    "0.",
)


def validate_media_url(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        raise InvalidUrlError("El enlace es obligatorio.")

    url = raw.strip()
    if len(url) > 2048:
        raise InvalidUrlError("El enlace es demasiado largo.")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise InvalidUrlError("Solo se aceptan enlaces http o https.")

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise InvalidUrlError("El enlace no tiene un host válido.")

    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        raise InvalidUrlError("Ese host no está permitido.")

    if host.startswith(_BLOCKED_PREFIXES) or host == "::1":
        raise InvalidUrlError("No se permiten direcciones locales o privadas.")

    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
        except (IndexError, ValueError):
            second = -1
        if 16 <= second <= 31:
            raise InvalidUrlError("No se permiten direcciones locales o privadas.")

    return url


def hostname_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()
