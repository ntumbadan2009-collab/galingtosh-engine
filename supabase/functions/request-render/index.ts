import { createClient } from "npm:@supabase/supabase-js@2";
import { corsHeaders, json } from "./cors.ts";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return json({ error: "Méthode non autorisée" }, 405);
  try {
    const token = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
    const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const { data: u, error: ue } = await admin.auth.getUser(token);
    if (ue || !u?.user) return json({ error: "Non authentifié" }, 401);
    const userId = u.user.id;

    const body = await req.json().catch(() => null);
    const projectId = body?.project_id;
    if (typeof projectId !== "string" || !UUID.test(projectId)) return json({ error: "project_id invalide" }, 400);

    const { data: project } = await admin.from("projects").select("id").eq("id", projectId).eq("user_id", userId).maybeSingle();
    if (!project) return json({ error: "Projet introuvable" }, 404);

    const { data: film } = await admin.from("films").select("data, version").eq("project_id", projectId)
      .order("version", { ascending: false }).limit(1).maybeSingle();
    if (!film) return json({ error: "Film introuvable" }, 404);
    const hasShots = (film.data?.scenes ?? []).some((s: any) => (s.shots ?? []).length > 0);
    if (!hasShots) return json({ error: "Le film ne contient aucun plan : rien à rendre." }, 422);

    const { data: jobId, error } = await admin.rpc("queue_render", { p_user_id: userId, p_project_id: projectId });
    if (error) return json({ error: error.message }, 422);
    return json({ job_id: jobId, status: "queued" });
  } catch (e) {
    console.error(e);
    return json({ error: "Erreur interne" }, 500);
  }
});

