import { createClient } from "npm:@supabase/supabase-js@2";
import { corsHeaders, json } from "./cors.ts";
import { loadMediaKeys, MEDIA_SEARCH_KINDS, MEDIA_SOURCES, searchMedia } from "./media.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return json({ error: "Méthode non autorisée" }, 405);
  try {
    const token = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
    const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const { data: u, error: ue } = await admin.auth.getUser(token);
    if (ue || !u?.user) return json({ error: "Non authentifié" }, 401);

    const body = await req.json().catch(() => null);
    const query = typeof body?.query === "string" ? body.query.trim() : "";
    const kind = body?.kind ?? "image";
    if (!query || query.length > 200) return json({ error: "query requis (1 à 200 caractères)" }, 400);
    if (!MEDIA_SEARCH_KINDS.includes(kind)) return json({ error: `kind invalide. Valeurs : ${MEDIA_SEARCH_KINDS.join(", ")}` }, 400);
    const sources = Array.isArray(body?.sources) ? body.sources.filter((s: unknown) => typeof s === "string" && MEDIA_SOURCES.includes(s)) : undefined;
    const limit = Number.isFinite(Number(body?.limit)) ? Number(body.limit) : 8;

    const keys = await loadMediaKeys(admin);
    return json(await searchMedia({ query, kind, limit, sources }, keys));
  } catch (e) {
    console.error(e);
    return json({ error: "Erreur interne" }, 500);
  }
});

