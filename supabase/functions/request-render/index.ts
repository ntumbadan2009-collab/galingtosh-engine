import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";
import { corsHeaders, json } from "./cors.ts";

declare const EdgeRuntime: { waitUntil(promise: Promise<unknown>): void };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ENGINE_ROOT = Deno.env.get("RENDER_ENGINE_URL") ?? "https://galingtosh-engine.onrender.com";

async function wakeRenderEngine(): Promise<void> {
  try {
    const response = await fetch(`${ENGINE_ROOT.replace(/\/$/, "")}/`, {
      method: "GET",
      signal: AbortSignal.timeout(120_000),
    });
    await response.body?.cancel();
    if (!response.ok) {
      console.warn(`Le réveil du moteur Render a répondu HTTP ${response.status}.`);
    } else {
      console.info("Le moteur Render a été réveillé après la mise en file du rendu.");
    }
  } catch (error) {
    console.warn("Le réveil du moteur Render a échoué; la tâche reste en file.", error);
  }
}

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

    const { data: film } = await admin.from("films").select("id, rev, data, version").eq("project_id", projectId)
      .order("version", { ascending: false }).limit(1).maybeSingle();
    if (!film) return json({ error: "Film introuvable" }, 404);
    const hasShots = (film.data?.scenes ?? []).some((s: any) => (s.shots ?? []).length > 0);
    if (!hasShots) return json({ error: "Le film ne contient aucun plan : rien à rendre." }, 422);

    const segments = (film.data?.scenes ?? []).flatMap((scene: any) => {
      const narration = scene.narration;
      if (!narration || typeof narration.text !== "string" || !narration.text.trim()) return [];
      return [{ sceneId: String(scene.id), text: narration.text, voice: narration.voice ?? "default",
        language: narration.language ?? film.data?.info?.language ?? "fr",
        targetDurationSec: narration.targetDurationSec ?? scene.durationSec }];
    });
    if (segments.length) {
      const measured = await fetch(`${ENGINE_ROOT.replace(/\/$/, "")}/narration/measure`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ segments }), signal: AbortSignal.timeout(105_000),
      });
      if (!measured.ok) return json({ error: "La durée de la narration n'a pas pu être vérifiée avant le rendu." }, 503);
      const measurement = await measured.json();
      const mismatches = (measurement.segments ?? []).filter((x: any) => {
        const actual = Number(x.durationSec), target = Number(x.targetDurationSec);
        return Number.isFinite(actual) && Number.isFinite(target) && Math.abs(actual - target) > Math.max(1, target * 0.1);
      });
      if (mismatches.length) return json({ code: "narration_needs_revision",
        error: "La narration doit être révisée par L’IA avant le rendu.", segments: mismatches }, 409);
      const alignedFilm = structuredClone(film.data);
      for (const measuredSegment of measurement.segments ?? []) {
        const scene = (alignedFilm.scenes ?? []).find((candidate: any) => String(candidate.id) === String(measuredSegment.sceneId));
        if (!scene?.narration) continue;
        const oldDuration = Number(scene.durationSec) || Number(measuredSegment.durationSec);
        const actualDuration = Number(measuredSegment.durationSec);
        if (!Number.isFinite(actualDuration) || actualDuration < 0.5 || actualDuration > 3600) continue;
        const ratio = actualDuration / oldDuration;
        for (const shot of scene.shots ?? []) {
          shot.inSec = Math.max(0, Number(shot.inSec ?? 0) * ratio);
          shot.outSec = Math.max(shot.inSec + 0.05, Number(shot.outSec ?? oldDuration) * ratio);
        }
        scene.durationSec = actualDuration;
        scene.narration.measuredDurationSec = actualDuration;
        if (measuredSegment.ttsProvider === "edge-tts" || measuredSegment.ttsProvider === "piper") scene.narration.ttsProvider = measuredSegment.ttsProvider;
      }
      const aligned = await admin.rpc("save_film_operation", {
        p_user_id: userId, p_film_id: film.id, p_rev: film.rev, p_data: alignedFilm,
        p_op: { name: "align_narration_durations", args: { segments: measurement.segments ?? [] } },
      });
      if (aligned.error || !aligned.data) return json({ code: "film_changed", error: "Le film a changé pendant la mesure TTS. Relance la vérification avant le rendu." }, 409);
    }

    const { data: jobId, error } = await admin.rpc("queue_render", { p_user_id: userId, p_project_id: projectId });
    if (error) return json({ error: error.message }, 422);
    EdgeRuntime.waitUntil(wakeRenderEngine());
    return json({ job_id: jobId, status: "queued" });
  } catch (e) {
    console.error(e);
    return json({ error: "Erreur interne" }, 500);
  }
});
