"""Conservative open-Web media discovery. No JavaScript, HTML imports or inferred rights."""
from __future__ import annotations
import asyncio, hashlib, json, re, tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from app.media.resolver import validate_remote_url, download_public_media

_BAD=re.compile(r"\b(?:pornography|pornhub|xxx|nsfw|hentai|gore|snuff|nudity|nude|sexually explicit)\b",re.I)
def public_https(value:str)->str:
    url=validate_remote_url(value)
    p=urlsplit(url)
    if p.scheme!="https" or p.port not in (None,443) or _BAD.search(url) or len(url)>2048:
        raise ValueError("URL publique HTTPS requise.")
    return url

def license_record(value):
    if not isinstance(value,str): return None
    try:
        p=urlsplit(value)
        if p.hostname not in {"creativecommons.org","www.creativecommons.org"} or p.scheme not in {"http","https"} or p.username or p.password or p.port: return None
        m=re.fullmatch(r"/licenses/by/(4\.0|3\.0|2\.5|2\.0|1\.0)/?",p.path)
        if m: return "CC BY "+m[1],"https://creativecommons.org/licenses/by/"+m[1]+"/"
        m=re.fullmatch(r"/publicdomain/(zero|mark)/1\.0/?",p.path)
        if m: return ("CC0 1.0" if m[1]=="zero" else "Public Domain Mark 1.0"),"https://creativecommons.org/publicdomain/"+m[1]+"/1.0/"
    except (TypeError,ValueError): pass
    return None

class _LD(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.capture=False;self.parts=[];self.blocks=[]
    def handle_starttag(self,tag,attrs):
        if tag=="script" and dict(attrs).get("type","").lower()=="application/ld+json":
            self.capture=True;self.parts=[]
    def handle_data(self,data):
        if self.capture: self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=="script" and self.capture:
            self.capture=False
            if len(self.blocks)<16: self.blocks.append("".join(self.parts))

def _nodes(value,depth=0):
    if depth>12:return
    if isinstance(value,list):
        for x in value[:100]: yield from _nodes(x,depth+1)
    elif isinstance(value,dict):
        yield value
        for key in ("@graph","image","video","associatedMedia","subjectOf","mainEntity","hasPart"):
            if key in value:yield from _nodes(value[key],depth+1)

def _name(value):
    if isinstance(value,list):return ", ".join(filter(None,(_name(v) for v in value[:5])))[:200]
    if isinstance(value,dict):value=value.get("name")
    return value.strip()[:200] if isinstance(value,str) else ""

def extract_candidates(html:str,page_url:str,kind:str):
    """Only a MediaObject's own license, creator and contentUrl count.
    A page-wide CC badge, Open Graph preview or a search result is not permission."""
    page=public_https(page_url);host=urlsplit(page).hostname
    parser=_LD();parser.feed(html[:2_000_000])
    out=[];seen=set()
    for block in parser.blocks:
        try: raw=json.loads(block)
        except (ValueError,RecursionError): continue
        for node in _nodes(raw):
            types=node.get("@type",[])
            if isinstance(types,str):types=[types]
            if not isinstance(types,list):continue
            types={str(x).rstrip("/").rsplit("/",1)[-1] for x in types}
            if ("ImageObject" if kind=="image" else "VideoObject") not in types:continue
            rights=license_record(node.get("license"));author=_name(node.get("creator") or node.get("author"))
            title=_name(node.get("name") or node.get("caption") or node.get("description"))
            if not rights or not author or not title or _BAD.search(author+" "+title):continue
            content=node.get("contentUrl")
            if not isinstance(content,str):continue
            try: url=public_https(urljoin(page,content))
            except (ValueError,TypeError):continue
            # Same-host or its subdomain only: do not infer that a page can
            # grant rights to assets from an unrelated third-party host.
            dest=urlsplit(url).hostname
            if not dest or not host or (dest!=host and not dest.endswith("."+host)):continue
            if url in seen:continue
            seen.add(url)
            ident=hashlib.sha256((page+"\n"+url).encode()).hexdigest()[:32]
            out.append(dict(id="web:"+ident,source="web",kind=kind,title=title,author=author,license=rights[0],license_url=rights[1],url=page,download_url=url,attribution=author+" — "+rights[0]+" — "+page,restrictions=["Attribution obligatoire"] if rights[0].startswith("CC BY") else []))
            if len(out)>=3:return out
    return out

async def licensed_page_candidates(url:str,kind:str):
    if kind not in {"image","video"}:return []
    page=public_https(url);host=urlsplit(page).hostname
    with tempfile.TemporaryDirectory(prefix="gt-web-page-") as work:
        path=Path(work)/"page"
        try:
            _,mime=await asyncio.wait_for(download_public_media(page,path,2_000_000,allowed_hosts=(host,)),timeout=9)
            if mime not in {"text/html","application/xhtml+xml"}:return []
            return extract_candidates(path.read_text(encoding="utf-8",errors="replace"),page,kind)
        except (OSError,ValueError,TimeoutError,RecursionError):return []
