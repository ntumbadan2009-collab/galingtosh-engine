// Registre d'outils de l'agent + exécuteur. Toute modification du film passe par applyOperation(),
// versionnée (rev) et journalisée dans film_operations (annulation possible).
import { applyOperation, defaultFilm, FILM_TYPES, MEDIA_KINDS, AUDIO_KINDS, type Json } from "./film.ts";
import { describeImage, type LlmCfg, type ToolDef } from "./llm.ts";
import { MEDIA_SEARCH_KINDS, MEDIA_SOURCES, searchMedia, loadMediaKeys } from "./media.ts";

export interface Ctx {
  admin: any;
  userId: string;
  conversationId: string;
  projectId: string | null;
  cfg: LlmCfg;
  usage: { input: number; output: number };
}
export interface ToolOut { output: any; metadata?: Json; isError?: boolean }

const S = (description?: string) => ({ type: "string", ...(description ? { description } : {}) });
const N = (description?: string) => ({ type: "number", ...(description ? { description } : {}) });
const E = (values: string[], description?: string) => ({ type: "string", enum: values, ...(description ? { description } : {}) });
const CAM = {
  type: "object", description: "Mouvement de caméra programmatique. type standard : ken_burns, dolly, pan, tilt, zoom_in, zoom_out, none. params libres (ex. direction, intensité).",
  properties: { type: S(), params: { type: "object" } }, required: ["type"],
};
const tool = (name: string, description: string, properties: Json = {}, required: string[] = []): ToolDef =>
  ({ name, description, input_schema: { type: "object", properties, required } });

export const TOOLS: ToolDef[] = [
  tool("create_project", "Crée un projet et son Film JSON vide, uniquement quand l'utilisateur demande clairement de commencer/enregistrer une production ou qu'une création est nécessaire pour exécuter sa demande. Ne pas appeler pour un salut, une question générale ou une simple exploration d'idée.",
    { title: S(), type: E(FILM_TYPES), language: S("code langue, ex. fr"), synopsis: S() }, ["title", "type"]),
  tool("get_film", "Retourne le Film JSON complet de la version de travail."),
  tool("set_project_info", "Modifie titre, type, langue ou synopsis.",
    { title: S(), type: E(FILM_TYPES), language: S(), synopsis: S() }),
  tool("set_format", "Définit le format vidéo. Recommande-le selon le projet (9:16 vertical réseaux sociaux, 16:9 documentaire/film, 1:1 ou 4:5 fil d'actualité, 21:9 cinéma, 4:3 archives).",
    { aspect: E(["16:9", "9:16", "1:1", "4:3", "4:5", "21:9", "custom"]), width: N("requis si custom, entier pair"), height: N("requis si custom, entier pair"), fps: N() }, ["aspect"]),
  tool("set_render_params", "Réglages de rendu.",
    { targetDurationSec: N(), resolution: E(["720p", "1080p"]), audioBitrateKbps: N(), videoBitrateMbps: N() }),
  tool("add_character", "Ajoute un personnage.", { name: S(), description: S(), voiceRef: S() }, ["name"]),
  tool("update_character", "Modifie un personnage.", { character_id: S(), name: S(), description: S(), voiceRef: S() }, ["character_id"]),
  tool("add_scene", "Ajoute une scène (position 1-based optionnelle, sinon à la fin).",
    { title: S(), narrativeGoal: S("intention dramatique/narrative"), durationSec: N(), mood: S(), characters: { type: "array", items: S() }, position: N() },
    ["title", "narrativeGoal", "durationSec"]),
  tool("update_scene", "Modifie une scène existante (champs partiels).",
    { scene_id: S(), title: S(), narrativeGoal: S(), durationSec: N(), mood: S(), characters: { type: "array", items: S() } }, ["scene_id"]),
  tool("remove_scene", "Supprime une scène et ses plans.", { scene_id: S() }, ["scene_id"]),
  tool("reorder_scenes", "Réordonne les scènes : fournir TOUS les ids dans le nouvel ordre.", { scene_ids: { type: "array", items: S() } }, ["scene_ids"]),
  tool("add_shot", "Ajoute un plan à une scène. inSec/outSec = bornes du plan dans la scène.",
    { scene_id: S(), camera: CAM, mediaRef: S("id d'un média déjà présent dans le film"), inSec: N(), outSec: N(), position: N() }, ["scene_id", "outSec"]),
  tool("update_shot", "Modifie un plan (mediaRef: null pour détacher le média).",
    { shot_id: S(), camera: CAM, mediaRef: { type: ["string", "null"] }, inSec: N(), outSec: N() }, ["shot_id"]),
  tool("remove_shot", "Supprime un plan.", { shot_id: S() }, ["shot_id"]),
  tool("set_transition", "Définit la transition appliquée au plan indiqué. Standard : cut, dissolve, fade, slide, zoom, wipe (autres types acceptés mais à supporter par le worker).",
    { at_shot_id: S(), type: S(), durationSec: N() }, ["at_shot_id", "type"]),
  tool("add_effect", "Ajoute un effet pris en charge : fade_in, fade_out, grayscale, vignette, text_overlay. params : text, position (top/center/bottom), fontSize, durationSec. target : film, id de scène ou de plan.",
    { type: S(), target: S("id de scène/plan/piste ou 'film'"), params: { type: "object" } }, ["type", "target"]),
  tool("remove_effect", "Supprime un effet.", { effect_id: S() }, ["effect_id"]),
  tool("add_audio_track", "Ajoute une piste audio : fichier ou voix off. Pour un effet sfx, fournis expectedContent et jusqu’à 3 candidats audio issus de search_media; le moteur les écoute avec CLAP local, rejette les échecs et essaie un effet procédural pris en charge en dernier recours.",
    { kind: E(AUDIO_KINDS), mediaRef: S(), expectedContent: S(), candidateMediaRefs: { type: "array", maxItems: 3, items: S() }, tts: { type: "object", properties: { text: S(), provider: S(), voice: S(), language: S() }, required: ["text"] },
      events: { type: "array", items: { type: "object", properties: { startSec: N(), durationSec: N() }, required: ["startSec", "durationSec"] } }, volumeDb: N() }, ["kind"]),
  tool("remove_audio_track", "Supprime une piste audio.", { track_id: S() }, ["track_id"]),
  tool("update_audio_track", "Corrige localement volume ou placement d'une piste existante, sans modifier les autres pistes.",
    { track_id: S(), volumeDb: N(), events: { type: "array", items: { type: "object", properties: { id: S(), startSec: N(), durationSec: N() }, required: ["startSec", "durationSec"] } } }, ["track_id"]),
  tool("set_procedural_music", "Active ou désactive l'instrumental procédural du film, ou règle son volume global. Désactive pour garder voix et effets sans musique.",
    { enabled: { type: "boolean" }, volumeDb: N() }),
  tool("set_scene_music", "Règle uniquement l'ambiance instrumentale d'une scène. silence la coupe; aucune autre scène n'est modifiée.",
    { scene_id: S(), mood: E(["silence", "calm", "hopeful", "tense", "sad", "wonder", "neutral"]), intensity: N("0 à 1") }, ["scene_id", "mood"]),
  tool("update_subtitles", "Remplace les sous-titres d'une langue (ou d'une piste).",
    { language: S(), track_id: S(), cues: { type: "array", items: { type: "object", properties: { startSec: N(), endSec: N(), text: S() }, required: ["startSec", "endSec", "text"] } } }, ["language", "cues"]),
  tool("search_media", "Cherche des médias existants (Wikimedia Commons, Openverse, Pexels, Pixabay, Freesound, Poly Haven). Retourne licence, auteur et restrictions : ne jamais les présenter comme « libres de droits » sans les citer.",
    { query: S(), kind: E(MEDIA_SEARCH_KINDS), limit: N(), sources: { type: "array", items: E(MEDIA_SOURCES) } }, ["query", "kind"]),
  tool("add_found_media", "Enregistre dans le projet un résultat de search_media (par son result_id) avec sa provenance, et l'attache éventuellement à un plan.",
    { result_id: S(), shot_id: S() }, ["result_id"]),
  tool("list_media", "Liste les médias du projet (imports de l'utilisateur et médias trouvés) avec leur analyse."),
  tool("register_uploaded_media", "Ajoute au Film JSON un média déjà importé par l'utilisateur, sans l'affecter à un plan. À utiliser si l'utilisateur demande de rattacher son fichier au projet mais n'a pas choisi de plan. Ne dis pas que le média est monté dans une scène : il est seulement enregistré dans les médias du film.", { media_asset_id: S() }, ["media_asset_id"]),
  tool("attach_media", "Attache un média existant du projet (media_asset_id) à un plan.", { shot_id: S(), media_asset_id: S() }, ["shot_id", "media_asset_id"]),
  tool("analyze_media", "Analyse une image du projet par vision (description, tags, personnes décrites, lieux, couleurs) et enregistre l'analyse. Lecture seule : aucune image n'est générée.",
    { media_asset_id: S() }, ["media_asset_id"]),
  tool("request_render", "Met le film en file de rendu (fige la version courante). Le rendu est exécuté par un worker externe : le résultat n'est pas immédiat."),
  tool("undo_last_operation", "Annule la dernière opération appliquée à la version de travail du film."),
];

const FILM_OPS = new Set([
  "set_project_info", "set_format", "set_render_params", "add_character", "update_character",
  "add_scene", "update_scene", "remove_scene", "reorder_scenes", "add_shot", "update_shot", "remove_shot",
  "set_transition", "add_effect", "remove_effect", "add_audio_track", "remove_audio_track", "update_audio_track", "set_procedural_music", "set_scene_music", "update_subtitles",
]);

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function loadWorking(ctx: Ctx) {
  const { data, error } = await ctx.admin.from("films").select("*").eq("project_id", ctx.projectId).eq("user_id", ctx.userId)
    .order("version", { ascending: false }).limit(1).maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) throw new Error("Film introuvable pour ce projet");
  return data;
}

export async function mutateFilm(ctx: Ctx, name: string, args: Json) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const row = await loadWorking(ctx);
    const { film, result } = applyOperation(row.data, name, args);
    const { data: saved, error } = await ctx.admin.rpc("save_film_operation", {
      p_user_id: ctx.userId, p_film_id: row.id, p_rev: row.rev, p_data: film, p_op: { name, args },
    });
    if (error) throw new Error(error.message);
    if (!saved) continue;
    return { ...result, film_version: row.version };
  }
  throw new Error("Conflit de modification simultanée, réessaie.");
}

async function createProject(ctx: Ctx, a: Json) {
  if (ctx.projectId) throw new Error("Un projet est déjà lié à cette conversation.");
  const type = FILM_TYPES.includes(a.type) ? a.type : (() => { throw new Error(`type invalide. Valeurs : ${FILM_TYPES.join(", ")}`); })();
  const title = typeof a.title === "string" && a.title.trim() ? a.title.trim().slice(0, 200) : (() => { throw new Error("title requis"); })();
  const film = defaultFilm(title, type, typeof a.language === "string" ? a.language.slice(0, 10) : "fr");
  if (typeof a.synopsis === "string" && a.synopsis.trim()) film.info.synopsis = a.synopsis.trim().slice(0, 4000);

  const { data: p, error } = await ctx.admin.from("projects").insert({ user_id: ctx.userId, title, type }).select("id").single();
  if (error) throw new Error(error.message);
  const { error: fe } = await ctx.admin.from("films").insert({ project_id: p.id, user_id: ctx.userId, version: 1, data: film });
  if (fe) {
    await ctx.admin.from("projects").delete().eq("id", p.id);
    throw new Error(fe.message);
  }
  await ctx.admin.from("conversations").update({ project_id: p.id }).eq("id", ctx.conversationId);
  ctx.projectId = p.id;
  return { ok: true, project_id: p.id, film_version: 1 };
}

function mediaRefFromRow(r: Json): Json {
  const m: Json = { id: r.id, kind: r.kind, source: r.source };
  if (r.storage_path) m.storagePath = r.storage_path;
  if (r.provenance) m.provenance = r.provenance;
  if (r.analysis) m.analysis = r.analysis;
  return m;
}

async function loadAsset(ctx: Ctx, id: any) {
  if (typeof id !== "string" || !UUID.test(id)) throw new Error("media_asset_id invalide");
  const { data } = await ctx.admin.from("media_assets").select("*").eq("id", id)
    .eq("project_id", ctx.projectId).eq("user_id", ctx.userId).eq("user_id", ctx.userId).maybeSingle();
  if (!data) throw new Error("Média introuvable dans ce projet");
  return data;
}

function parseJsonLoose(t: string): Json {
  const m = t.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("Réponse de vision non exploitable");
  return JSON.parse(m[0]);
}
const list = (v: any) => (Array.isArray(v) ? v.filter((x) => typeof x === "string").slice(0, 12).map((x) => x.slice(0, 120)) : []);

const VISION_PROMPT =
  "Analyse cette image pour un montage audiovisuel. Réponds UNIQUEMENT par un objet JSON : " +
  '{"description": string, "tags": string[], "people": string[], "places": string[], "colors": string[]}. ' +
  "people : décris les personnes visibles (ex. « femme âgée en robe bleue ») sans JAMAIS identifier une personne réelle à son visage ; " +
  "n'indique un nom que s'il est écrit de façon visible dans l'image (légende, badge). " +
  "places : seulement les lieux identifiables par des éléments visibles (panneau, monument connu), sinon le type de lieu. " +
  "colors : 3 à 5 couleurs dominantes. Rédige en français.";

export async function execTool(ctx: Ctx, name: string, args: Json): Promise<ToolOut> {
  try {
    if (name === "create_project") return { output: await createProject(ctx, args) };

    if (name === "search_media") {
      const query = typeof args.query === "string" ? args.query.trim().slice(0, 200) : "";
      if (!query) throw new Error("query requis");
      if (!MEDIA_SEARCH_KINDS.includes(args.kind)) throw new Error(`kind invalide. Valeurs : ${MEDIA_SEARCH_KINDS.join(", ")}`);
      const sources = Array.isArray(args.sources) ? args.sources.filter((s: any) => MEDIA_SOURCES.includes(s)) : undefined;
      const r = await searchMedia({ query, kind: args.kind, limit: Number(args.limit) || 8, sources }, await loadMediaKeys(ctx.admin));
      const compact = r.results.map((x) => ({
        result_id: x.id, title: x.title, author: x.author, license: x.license, restrictions: x.restrictions,
        source: x.source, url: x.url, width: x.width, height: x.height, duration: x.duration,
      }));
      return {
        output: { results: compact, searched: r.searched, skipped: r.skipped, errors: r.errors },
        metadata: { kind: "search_media", results: r.results },
      };
    }

    if (!ctx.projectId) throw new Error("Aucun projet n'est lié à cette conversation. Appelle d'abord create_project.");
    if (FILM_OPS.has(name)) return { output: await mutateFilm(ctx, name, args) };

    switch (name) {
      case "get_film": {
        const row = await loadWorking(ctx);
        return { output: { version: row.version, rev: row.rev, film: row.data } };
      }
      case "list_media": {
        const { data, error } = await ctx.admin.from("media_assets")
          .select("id, kind, source, storage_path, license, analysis, created_at")
          .eq("project_id", ctx.projectId).eq("user_id", ctx.userId).order("created_at");
        if (error) throw new Error(error.message);
        return { output: { media: data } };
      }
      case "register_uploaded_media": {
        const row = await loadAsset(ctx, args.media_asset_id);
        const result = await mutateFilm(ctx, "register_media", { media: mediaRefFromRow(row) });
        return { output: { ok: true, ...result, media_asset_id: row.id, registered_in_film: true, attached_to_shot: false } };
      }
      case "add_found_media": {
        const rid = String(args.result_id ?? "");
        const { data: msgs } = await ctx.admin.from("messages").select("metadata")
          .eq("conversation_id", ctx.conversationId).eq("role", "tool")
          .contains("metadata", { kind: "search_media" }).order("created_at", { ascending: false }).limit(30);
        let found: Json | undefined;
        for (const m of msgs ?? []) {
          found = (m.metadata?.results ?? []).find((r: Json) => r.id === rid);
          if (found) break;
        }
        if (!found) throw new Error("result_id inconnu : il doit provenir d'un search_media de cette conversation.");

        if (args.shot_id) {
          const working = await loadWorking(ctx);
          if (!(working.data.scenes ?? []).some((s:Json)=>(s.shots ?? []).some((p:Json)=>p.id===args.shot_id))) throw new Error("shot_id doit désigner un PLAN existant, pas une scène. Crée le plan avec add_shot avant d'y attacher le média.");
        }
        const { data: existing } = await ctx.admin.from("media_assets").select("*")
          .eq("project_id", ctx.projectId).eq("user_id", ctx.userId).eq("provenance->>result_id", rid).maybeSingle();
        let row = existing;
        if (!row) {
          const provenance = {
            result_id: rid, author: found.author, source: found.source, license: found.license,
            license_url: found.license_url ?? null, url: found.url, attribution: found.attribution ?? null,
            restrictions: found.restrictions ?? [], preview_url: found.preview_url ?? null,
            download_url: found.download_url ?? null, title: found.title,
          };
          const ins = await ctx.admin.from("media_assets").insert({
            project_id: ctx.projectId, user_id: ctx.userId, kind: found.kind, source: "search",
            license: found.license, provenance,
          }).select("*").single();
          if (ins.error) throw new Error(ins.error.message);
          row = ins.data;
        }
        const ref = mediaRefFromRow(row);
        const out = args.shot_id
          ? await mutateFilm(ctx, "attach_media", { shot_id: args.shot_id, media: ref })
          : await mutateFilm(ctx, "register_media", { media: ref });
        return { output: { ...out, media_asset_id: row.id, license: found.license, restrictions: found.restrictions } };
      }
      case "attach_media": {
        const row = await loadAsset(ctx, args.media_asset_id);
        return { output: await mutateFilm(ctx, "attach_media", { shot_id: args.shot_id, media: mediaRefFromRow(row) }) };
      }
      case "analyze_media": {
        const row = await loadAsset(ctx, args.media_asset_id);
        if (row.kind !== "image") throw new Error("L'analyse par vision ne concerne que les images.");
        let url: string | null = null;
        if (row.storage_path) {
          const parts = row.storage_path.split("/");
          if (parts[0] !== ctx.userId || parts.some((p:string)=>!p || p === "." || p === ".." || p.includes("\\"))) throw new Error("Chemin de média privé invalide.");
          const { data } = await ctx.admin.storage.from("user-uploads").createSignedUrl(row.storage_path, 600);
          url = data?.signedUrl ?? null;
        } else {
          url = row.provenance?.preview_url ?? row.provenance?.download_url ?? null;
        }
        if (!url) throw new Error("Aucune URL d'image exploitable pour ce média.");
        const r = await describeImage(ctx.cfg, url, VISION_PROMPT);
        ctx.usage.input += r.usage.input; ctx.usage.output += r.usage.output;
        const j = parseJsonLoose(r.text);
        const analysis = {
          description: typeof j.description === "string" ? j.description.slice(0, 1000) : undefined,
          tags: list(j.tags), people: list(j.people), places: list(j.places), colors: list(j.colors),
        };
        await ctx.admin.from("media_assets").update({ analysis }).eq("id", row.id);
        await mutateFilm(ctx, "update_media_analysis", { media_id: row.id, analysis });
        return { output: { ok: true, media_asset_id: row.id, analysis } };
      }
      case "request_render": {
        const row = await loadWorking(ctx);
        const hasShots = (row.data.scenes ?? []).some((s: Json) => (s.shots ?? []).length > 0);
        if (!hasShots) throw new Error("Le film ne contient aucun plan : rien à rendre.");
        const { data: jobId, error } = await ctx.admin.rpc("queue_render", { p_user_id: ctx.userId, p_project_id: ctx.projectId });
        if (error) throw new Error(error.message);
        return {
          output: {
            ok: true, job_id: jobId, status: "queued",
            note: "Rendu mis en file d'attente. Il sera exécuté par le worker de rendu ; la progression est suivie dans render_jobs. Ne pas annoncer que la vidéo est prête tant que le statut n'est pas 'done'.",
          },
          metadata: { kind: "render_job", job_id: jobId },
        };
      }
      case "undo_last_operation": {
        const { data: name, error } = await ctx.admin.rpc("undo_film_operation", { p_user_id: ctx.userId, p_project_id: ctx.projectId });
        if (error) throw new Error(error.message);
        return { output: { ok: true, undone: name } };
      }
      default:
        throw new Error(`Outil inconnu : ${name}`);
    }
  } catch (e) {
    return { output: { error: e instanceof Error ? e.message : String(e) }, isError: true };
  }
}

