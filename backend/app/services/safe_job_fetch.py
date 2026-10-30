"""Bounded, DNS-pinned HTTP reads for candidate-submitted job URLs."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx


MAX_RESPONSE_BYTES = 2_000_000
MAX_REDIRECTS = 4
ALLOWED_CONTENT_TYPES = ("text/html", "application/json", "application/ld+json", "text/plain")
BLOCKED_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp")


class UnsafeJobURL(ValueError):
    pass


class JobFetchError(ValueError):
    pass


@dataclass(frozen=True)
class FetchedPage:
    url: str
    status_code: int
    content_type: str
    text: str


def validate_job_url(url: str) -> str:
    if any(ord(char) < 32 for char in url):
        raise UnsafeJobURL("Control characters are not accepted in job URLs.")
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeJobURL("Only public http(s) job URLs are accepted.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeJobURL("The job URL has an invalid port.") from exc
    if parsed.username or parsed.password or port not in {None, 80, 443}:
        raise UnsafeJobURL("Credentials and nonstandard ports are not accepted in job URLs.")
    host = parsed.hostname.rstrip(".").lower()
    if "." not in host or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise UnsafeJobURL("Private or internal job URLs are not accepted.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise UnsafeJobURL("Private or internal job URLs are not accepted.")
    return url.strip()


async def _public_addresses(host: str, port: int) -> list[str]:
    try:
        records = await asyncio.wait_for(
            asyncio.to_thread(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM),
            timeout=3,
        )
    except (OSError, TimeoutError) as exc:
        raise JobFetchError("The job host could not be resolved.") from exc
    addresses = list(dict.fromkeys(record[4][0] for record in records))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise UnsafeJobURL("The job URL resolves to a private or internal address.")
    return addresses


async def fetch_job_page(
    url: str, *, method: str = "GET", json_body: dict | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> FetchedPage:
    """Validate each hop and connect to a validated IP, preventing DNS rebinding."""
    current = validate_job_url(url)
    if method not in {"GET", "POST"}:
        raise ValueError("Unsupported job-fetch method")
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8, connect=4), follow_redirects=False,
        trust_env=False, headers={"User-Agent": "InternshipRadar/1.0 job-import"},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            parsed = urlsplit(current)
            host = parsed.hostname or ""
            addresses = await _public_addresses(host, parsed.port or (443 if parsed.scheme == "https" else 80))
            # The URL used by the transport contains a checked IP, while Host
            # and TLS SNI retain the employer hostname for HTTP routing/cert checks.
            pinned = httpx.URL(current).copy_with(host=addresses[0])
            try:
                async with client.stream(
                    method, pinned, headers={"Host": parsed.netloc},
                    json=json_body, extensions={"sni_hostname": host},
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        destination = response.headers.get("location")
                        if not destination:
                            raise JobFetchError("The job page redirected without a destination.")
                        current = validate_job_url(urljoin(current, destination))
                        if response.status_code == 303:
                            method, json_body = "GET", None
                        continue
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type not in ALLOWED_CONTENT_TYPES:
                        raise JobFetchError("The job page returned an unsupported content type.")
                    try:
                        declared_length = int(response.headers.get("content-length") or 0)
                    except ValueError as exc:
                        raise JobFetchError("The job page returned an invalid response size.") from exc
                    if declared_length > max_bytes:
                        raise JobFetchError("The job page is too large to import safely.")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise JobFetchError("The job page is too large to import safely.")
                        chunks.append(chunk)
                    if response.status_code >= 500:
                        raise JobFetchError("The job source is temporarily unavailable.")
                    return FetchedPage(current, response.status_code, content_type, b"".join(chunks).decode("utf-8", "replace"))
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise JobFetchError("The job source could not be reached safely.") from exc
    raise JobFetchError("The job page redirected too many times.")
