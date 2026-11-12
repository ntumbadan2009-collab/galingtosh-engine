from __future__ import annotations
import asyncio, ipaddress, socket
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
import aiohttp

MAX_REMOTE_BYTES = 200 * 1024 * 1024
REDIRECT_CODES = {301,302,303,307,308}
class UnsafeMediaURL(ValueError): pass

class SafePublicResolver(aiohttp.abc.AbstractResolver):
    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        try:
            ip = ipaddress.ip_address(host)
            addresses = [str(ip)]
        except ValueError:
            records = await asyncio.get_running_loop().getaddrinfo(
                host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
            addresses = list(dict.fromkeys(x[4][0] for x in records))
        if not addresses: raise OSError("Hôte média introuvable.")
        result = []
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global: raise OSError("Destination réseau privée ou réservée refusée.")
            result.append({"hostname":host,"host":address,"port":port,
                "family":socket.AF_INET6 if ip.version==6 else socket.AF_INET,
                "proto":0,"flags":socket.AI_NUMERICHOST})
        return result
    async def close(self): return None

def validate_remote_url(url: str) -> str:
    try:
        p=urlsplit(url)
        if p.scheme.lower() not in {"http","https"} or not p.hostname or p.username or p.password:
            raise UnsafeMediaURL("URL média invalide.")
        if p.port not in (None,80,443): raise UnsafeMediaURL("Port réseau refusé.")
        try:
            if not ipaddress.ip_address(p.hostname).is_global:
                raise UnsafeMediaURL("Adresse réseau privée ou réservée refusée.")
        except ValueError:
            if p.hostname.lower() in {"localhost","localhost.localdomain"} or "." not in p.hostname:
                raise UnsafeMediaURL("Nom d’hôte local refusé.")
        return urlunsplit((p.scheme.lower(),p.netloc,p.path,p.query,""))
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc,UnsafeMediaURL): raise
        raise UnsafeMediaURL("URL média invalide.") from None

async def download_public_media(url: str, destination: Path, max_bytes: int = MAX_REMOTE_BYTES) -> tuple[int, str]:
    current=validate_remote_url(url)
    connector=aiohttp.TCPConnector(resolver=SafePublicResolver(),use_dns_cache=False,limit=2)
    timeout=aiohttp.ClientTimeout(total=45,connect=10,sock_read=20)
    destination.parent.mkdir(parents=True,exist_ok=True)
    try:
        async with aiohttp.ClientSession(connector=connector,timeout=timeout) as session:
            for hop in range(4):
                async with session.get(current,allow_redirects=False) as response:
                    if response.status in REDIRECT_CODES:
                        location=response.headers.get("Location")
                        if not location or hop==3: raise UnsafeMediaURL("Redirection média refusée.")
                        current=validate_remote_url(urljoin(current,location)); continue
                    if response.status<200 or response.status>=300: raise OSError("Téléchargement média refusé.")
                    content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
                    if response.content_length and response.content_length>max_bytes: raise OSError("Média trop volumineux.")
                    total=0
                    with destination.open("wb") as out:
                        async for chunk in response.content.iter_chunked(65536):
                            total+=len(chunk)
                            if total>max_bytes: raise OSError("Média trop volumineux.")
                            out.write(chunk)
                    if not total: raise OSError("Média distant vide.")
                    return total, content_type
        raise OSError("Téléchargement interrompu.")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
