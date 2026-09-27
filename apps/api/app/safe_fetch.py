"""Bounded public URL fetching with DNS pinning and redirect revalidation."""
import asyncio
import ipaddress
import socket

import httpx


async def public_target(url: str) -> tuple[httpx.URL, str]:
    target = httpx.URL(url)
    if target.scheme not in ("http", "https") or not target.host or target.username or target.password or target.port not in (None, 80, 443):
        raise ValueError("Only public HTTP(S) listing URLs are supported")
    host = target.host.rstrip(".").lower()
    if host == "facebook.com" or host.endswith(".facebook.com") or host in ("fb.com", "fb.me"):
        raise ValueError("For Facebook Marketplace, upload a screenshot or enter the item details; open the original listing to purchase")
    addresses = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, target.port or (443 if target.scheme == "https" else 80), type=socket.SOCK_STREAM), timeout=5)
    ips = {row[4][0] for row in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError("Private, local and metadata network addresses are not allowed")
    # Connect to the validated IP, while TLS verifies the original host (prevents DNS rebinding).
    return target.copy_with(host=sorted(ips)[0]), host


async def fetch_public(url: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
        for _ in range(4):
            pinned, hostname = await public_target(url)
            async with client.stream("GET", pinned, headers={"Host": hostname, "User-Agent": "AdaptiveRoomPlanner/0.2"}, extensions={"sni_hostname": hostname}) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Listing redirect is missing a destination")
                    url = str(httpx.URL(url).join(location))
                    continue
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 8 * 1024 * 1024:
                        raise ValueError("Listing exceeds the 8 MB import limit")
                    chunks.append(chunk)
                return b"".join(chunks), response.headers.get("content-type", "").split(";")[0]
    raise ValueError("Too many listing redirects")
