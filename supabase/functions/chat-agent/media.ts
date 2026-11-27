import {artInstitute,archiveSearch,discoverWeb,safeMetadata,extendedEnabled,extendedSource} from "./web_media.ts";
// Recherche centralisée de médias. Les clés API restent côté serveur (Vault via get_media_keys(), sinon variables d'environnement).
// Chaque résultat conserve sa provenance : auteur, source, licence, URL, restrictions.
// Aucun média n'est jamais présenté comme « libre de droits » par défaut.

export interface MediaResult {
  id: string;
  source: string;
  kind: string;
  subtype?: string;
  title: string;
  author: string;
  license: string;
  license_url?: string;
  restrictions: string[];
  url: string;
  preview_url?: string;
  download_url?: string;
  width?: number;
  height?: number;
  duration?: number;
  size_bytes?: number;
  attribution?: string;
  published_at?: string;
}

export type Keys = Record<string, string>;
type Q = { query: string; kind: string; limit: number; keys: Keys };
type Raw = Omit<MediaResult, "restrictions">;

const UA = "Galingtosh/0.1 (media search)";
const NO_AUTHOR = "Auteur non précisé";
const NO_LICENSE = "Licence non précisée";

const KEY_NAMES = ["PIXABAY_API_KEY", "PEXELS_API_KEY", "FREESOUND_API_KEY", "BRAVE_SEARCH_API_KEY"];
let keysCache: { at: number; k: Keys } | null = null;

// Clés des fournisseurs de médias : Vault (via get_media_keys, service_role uniquement) puis variables d'environnement.
export async function loadMediaKeys(admin?: any): Promise<Keys> {
  if (keysCache && Date.now() - keysCache.at < 60_000) return keysCache.k;
  const k: Keys = {};
  for (const n of KEY_NAMES) {
    const v = Deno.env.get(n);
    if (v) k[n] = v;
  }
  if (admin) {
    try {
      const { data, error } = await admin.rpc("get_media_keys");
      if (error) throw error;
      for (const n of KEY_NAMES) if (data?.[n]) k[n] = String(data[n]);
    } catch (e) {
      console.error("get_media_keys:", e instanceof Error ? e.message : e);
    }
  }
  keysCache = { at: Date.now(), k };
  return k;
}

async function getJson(url: string, headers: Record<string, string> = {}) {
  const r = await fetch(url, {
    headers: { "User-Agent": UA, Accept: "application/json", ...headers },
    signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

const strip = (h?: string) =>
  (h ?? "").replace(/<[^>]*>/g, "").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/\s+/g, " ").trim();

function ccLabel(url?: string): string {
  if (!url) return NO_LICENSE;
  let m = url.match(/licenses\/([a-z-]+)\/([\d.]+)/i);
  if (m) return `CC ${m[1].toUpperCase()} ${m[2]}`;
  m = url.match(/publicdomain\/zero\/([\d.]+)/i);
  if (m) return `CC0 ${m[1]}`;
  return url;
}

function restrictionsFor(license: string): string[] {
  const l = license.toUpperCase();
  const out: string[] = [];
  if (l === NO_LICENSE.toUpperCase()) return ["Licence inconnue : vérifier la page source avant tout usage"];
  if (l.startsWith("PIXABAY")) {
    return [
      "Licence propre à Pixabay : utilisation dans une création possible sans attribution obligatoire, mais revente ou redistribution du fichier seul interdite ; personnes et marques identifiables : usage limité (voir la licence)",
      "Afficher la source Pixabay aux utilisateurs lors des résultats de recherche",
    ];
  }
  if (l.startsWith("PEXELS")) return ["Licence propre à Pexels : voir les conditions sur la page de la licence"];
  if (/\bBY\b/.test(l.replace(/-/g, " "))) out.push("Attribution obligatoire");
  if (l.includes("NC")) out.push("Usage non commercial uniquement");
  if (l.includes("SA")) out.push("Partage dans les mêmes conditions");
  if (l.includes("ND")) out.push("Modification interdite (montage/recadrage à vérifier)");
  return out;
}

// --- Wikimedia Commons (sans clé) ---
async function wikimedia({ query, kind, limit }: Q): Promise<Raw[]> {
  const ft = ({ image: "bitmap", video: "video", audio: "audio" } as Record<string, string>)[kind];
  if (!ft) return [];
  const u = new URL("https://commons.wikimedia.org/w/api.php");
  const p: Record<string, string> = {
    action: "query", generator: "search", gsrnamespace: "6",
    gsrsearch: `${query} filetype:${ft}`, gsrlimit: String(Math.min(limit, 20)),
    prop: "imageinfo", iiprop: "url|extmetadata|size|mime", iiurlwidth: "800",
    iiextmetadatafilter: "LicenseShortName|LicenseUrl|Artist|AttributionRequired",
    format: "json", formatversion: "2",
  };
  for (const [k, v] of Object.entries(p)) u.searchParams.set(k, v);
  const j = await getJson(u.toString());
  return (j.query?.pages ?? []).filter((pg: any) => pg.imageinfo?.[0]).map((pg: any) => {
    const ii = pg.imageinfo[0];
    const md = ii.extmetadata ?? {};
    const author = strip(md.Artist?.value) || NO_AUTHOR;
    const license = strip(md.LicenseShortName?.value) || NO_LICENSE;
    return {
      id: `wikimedia:${pg.pageid}`, source: "wikimedia", kind,
      title: String(pg.title ?? "").replace(/^File:/, ""),
      author, license, license_url: md.LicenseUrl?.value,
      url: ii.descriptionurl, preview_url: ii.thumburl ?? ii.url, download_url: ii.url,
      width: ii.width, height: ii.height,
      attribution: `${author} — ${license} — ${ii.descriptionurl}`,
    };
  });
}

// --- Openverse (sans clé, quota anonyme) ---
async function openverse({ query, kind, limit }: Q): Promise<Raw[]> {
  const ep = kind === "image" ? "images" : kind === "audio" ? "audio" : null;
  if (!ep) return [];
  const j = await getJson(
    `https://api.openverse.org/v1/${ep}/?q=${encodeURIComponent(query)}&page_size=${Math.min(limit, 20)}&mature=false`,
  );
  return (j.results ?? []).map((r: any) => ({
    id: `openverse:${r.id}`, source: "openverse", kind,
    title: r.title || "Sans titre", author: r.creator || NO_AUTHOR,
    license: r.license ? `${String(r.license).toUpperCase()}${r.license_version ? " " + r.license_version : ""}` : NO_LICENSE,
    license_url: r.license_url, url: r.foreign_landing_url || r.url,
    preview_url: r.thumbnail || r.url, download_url: r.url,
    width: r.width, height: r.height, duration: r.duration ? r.duration / 1000 : undefined,
    attribution: r.attribution,
  }));
}

// --- Pixabay (clé PIXABAY_API_KEY) : photos, illustrations, vecteurs, vidéos ---
// Règles Pixabay : mise en cache des requêtes 24 h, pas de hotlinking permanent (les fichiers choisis
// sont copiés dans le stockage du projet par add_found_media), source Pixabay affichée aux utilisateurs.
const PIX_TTL = 24 * 3600 * 1000;
const pixCache = new Map<string, { at: number; v: Raw[] }>();
async function pixCached(key: string, fn: () => Promise<Raw[]>): Promise<Raw[]> {
  const hit = pixCache.get(key);
  if (hit && Date.now() - hit.at < PIX_TTL) return hit.v;
  const v = await fn();
  if (pixCache.size >= 200) pixCache.delete(pixCache.keys().next().value as string);
  pixCache.set(key, { at: Date.now(), v });
  return v;
}

async function pixabay({ query, kind, limit, keys }: Q): Promise<Raw[]> {
  const key = keys.PIXABAY_API_KEY;
  const n = Math.max(3, Math.min(limit, 50));
  const q = query.slice(0, 100);
  const common = `key=${encodeURIComponent(key)}&q=${encodeURIComponent(q)}&per_page=${n}&safesearch=true`;
  const license = "Pixabay Content License";
  const license_url = "https://pixabay.com/service/license-summary/";
  if (kind === "image" || kind === "illustration" || kind === "vector") {
    const type = kind === "image" ? "photo" : kind;
    return pixCached(`img|${type}|${n}|${q.toLowerCase()}`, async () => {
      const j = await getJson(`https://pixabay.com/api/?${common}&image_type=${type}`);
      return (j.hits ?? []).slice(0, limit).map((h: any) => ({
        id: `pixabay:${h.id}`, source: "pixabay", kind: "image", subtype: type, title: h.tags || "Sans titre",
        author: h.user || NO_AUTHOR, license, license_url, url: h.pageURL,
        preview_url: h.webformatURL, download_url: h.fullHDURL || h.largeImageURL,
        width: h.imageWidth, height: h.imageHeight,
        attribution: `Pixabay — ${h.user || NO_AUTHOR} — ${h.pageURL}`,
      }));
    });
  }
  if (kind === "video") {
    return pixCached(`vid|${n}|${q.toLowerCase()}`, async () => {
      const j = await getJson(`https://pixabay.com/api/videos/?${common}`);
      return (j.hits ?? []).slice(0, limit).map((h: any) => {
        // rendition « medium » (en général 1080p) : assez légère pour être copiée dans le stockage (50 Mo max)
        const v = h.videos?.medium?.url ? h.videos.medium : h.videos?.small;
        return {
          id: `pixabay:${h.id}`, source: "pixabay", kind: "video", subtype: "video", title: h.tags || "Sans titre",
          author: h.user || NO_AUTHOR, license, license_url, url: h.pageURL,
          preview_url: v?.thumbnail ?? h.videos?.medium?.thumbnail, download_url: v?.url,
          width: v?.width, height: v?.height, duration: h.duration, size_bytes: v?.size || undefined,
          attribution: `Pixabay — ${h.user || NO_AUTHOR} — ${h.pageURL}`,
        };
      }).filter((x: Raw) => x.download_url);
    });
  }
  return [];
}

// --- Pexels (PEXELS_API_KEY) ---
async function pexels({ query, kind, limit, keys }: Q): Promise<Raw[]> {
  const headers = { Authorization: keys.PEXELS_API_KEY };
  const n = Math.max(1, Math.min(limit, 40));
  const license = "Pexels License";
  const license_url = "https://www.pexels.com/license/";
  if (kind === "image") {
    const j = await getJson(`https://api.pexels.com/v1/search?query=${encodeURIComponent(query)}&per_page=${n}`, headers);
    return (j.photos ?? []).map((p: any) => ({
      id: `pexels:${p.id}`, source: "pexels", kind, title: p.alt || "Sans titre",
      author: p.photographer || NO_AUTHOR, license, license_url, url: p.url,
      preview_url: p.src?.medium, download_url: p.src?.original, width: p.width, height: p.height,
    }));
  }
  if (kind === "video") {
    const j = await getJson(`https://api.pexels.com/videos/search?query=${encodeURIComponent(query)}&per_page=${n}`, headers);
    return (j.videos ?? []).map((v: any) => {
      const files = (v.video_files ?? []).filter((f: any) => f.file_type === "video/mp4" && f.width <= 1920);
      files.sort((a: any, b: any) => b.width - a.width);
      const best = files[0];
      return {
        id: `pexels:${v.id}`, source: "pexels", kind, title: `Vidéo Pexels ${v.id}`,
        author: v.user?.name || NO_AUTHOR, license, license_url, url: v.url,
        preview_url: v.image, download_url: best?.link, width: best?.width ?? v.width,
        height: best?.height ?? v.height, duration: v.duration,
      };
    });
  }
  return [];
}

// --- Freesound (FREESOUND_API_KEY) : aperçus audio uniquement ---
async function freesound({ query, kind, limit, keys }: Q): Promise<Raw[]> {
  if (kind !== "audio") return [];
  const key = keys.FREESOUND_API_KEY;
  const j = await getJson(
    `https://freesound.org/apiv2/search/text/?query=${encodeURIComponent(query)}&page_size=${Math.min(limit, 30)}` +
      `&fields=id,name,username,license,url,previews,duration&token=${encodeURIComponent(key)}`,
  );
  return (j.results ?? []).map((r: any) => ({
    id: `freesound:${r.id}`, source: "freesound", kind, title: r.name || "Sans titre",
    author: r.username || NO_AUTHOR, license: ccLabel(r.license), license_url: r.license,
    url: r.url, preview_url: r.previews?.["preview-lq-mp3"], download_url: r.previews?.["preview-hq-mp3"],
    duration: r.duration, attribution: `${r.username} — ${ccLabel(r.license)} — ${r.url}`,
  }));
}

// --- Poly Haven (sans clé) : modèles 3D CC0 ---
async function polyhaven({ query, kind, limit }: Q): Promise<Raw[]> {
  if (kind !== "model3d") return [];
  const j = await getJson("https://api.polyhaven.com/assets?t=models");
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  const out: Raw[] = [];
  for (const [id, a] of Object.entries<any>(j)) {
    const hay = `${a.name} ${(a.categories ?? []).join(" ")} ${(a.tags ?? []).join(" ")}`.toLowerCase();
    if (!terms.every((t) => hay.includes(t))) continue;
    out.push({
      id: `polyhaven:${id}`, source: "polyhaven", kind, title: a.name,
      author: Object.keys(a.authors ?? {}).join(", ") || "Poly Haven",
      license: "CC0 1.0", license_url: "https://creativecommons.org/publicdomain/zero/1.0/",
      url: `https://polyhaven.com/a/${id}`,
      preview_url: `https://cdn.polyhaven.com/asset_img/thumbs/${id}.png?width=512`,
      download_url: `https://api.polyhaven.com/files/${id}`,
    });
    if (out.length >= limit) break;
  }
  return out;
}

const ADAPTERS: Record<string, { env?: string; kinds: string[]; fn: (q: Q) => Promise<Raw[]> }> = {
  wikimedia: { kinds: ["image", "video", "audio"], fn: wikimedia },
  openverse: { kinds: ["image", "audio"], fn: openverse },
  pexels: { env: "PEXELS_API_KEY", kinds: ["image", "video"], fn: pexels },
  pixabay: { env: "PIXABAY_API_KEY", kinds: ["image", "illustration", "vector", "video"], fn: pixabay },
  freesound: { env: "FREESOUND_API_KEY", kinds: ["audio"], fn: freesound },
  artic: { kinds: ["image","illustration"], fn: ({query,limit})=>artInstitute(query,limit) },
  archive: { kinds: ["image","video"], fn: ({query,kind,limit})=>archiveSearch(query,kind,limit) },
  polyhaven: { kinds: ["model3d"], fn: polyhaven },
};

export const MEDIA_SEARCH_KINDS = ["image", "illustration", "vector", "video", "model3d"];
export const MEDIA_SOURCES = Object.keys(ADAPTERS);

export async function searchMedia(
  p: { query: string; kind: string; limit?: number; sources?: string[] },
  keys: Keys = {},
) {
  const limit = Math.max(1, Math.min(p.limit ?? 8, 20));
  const wanted = (p.sources?.length ? p.sources : Object.keys(ADAPTERS)).filter((s) => ADAPTERS[s]);
  const skipped: Record<string, string> = {};
  const active: string[] = [];
  for (const s of wanted) {
    const a = ADAPTERS[s];
    if (!a.kinds.includes(p.kind)) continue;
    if (extendedSource(s) && !extendedEnabled()) { skipped[s]='extension en quarantaine; validation requise'; continue; }
    if (a.env && !keys[a.env]) { skipped[s] = `clé ${a.env} non configurée`; continue; }
    active.push(s);
  }
  const errors: Record<string, string> = {};
  const discovery = keys.BRAVE_SEARCH_API_KEY && safeMetadata(p.query)
    ? discoverWeb(p.query,p.kind,keys.BRAVE_SEARCH_API_KEY,limit).catch(()=>[])
    : Promise.resolve([]);
  const settled = await Promise.allSettled(active.map((s) => ADAPTERS[s].fn({ query: p.query, kind: p.kind, limit, keys })));
  const lists: MediaResult[][] = [];
  settled.forEach((r, i) => {
    if (r.status === "fulfilled") {
      lists.push(r.value.filter(x=>safeMetadata(x.title,x.author,x.url,x.download_url,x.preview_url)).map((x) => ({ ...x, ...(extendedSource(x.source)?{preview_url:undefined}:{}), restrictions: restrictionsFor(x.license) })));
    } else {
      errors[active[i]] = String(r.reason?.message ?? r.reason).slice(0, 120);
    }
  });
  // entrelacement pour varier les sources
  const results: MediaResult[] = [];
  for (let i = 0; results.length < limit; i++) {
    let any = false;
    for (const l of lists) {
      if (l[i]) { any = true; if (results.length < limit) results.push(l[i]); }
    }
    if (!any) break;
  }
  return { results, searched: active, skipped, errors, web_references:await discovery };
}

