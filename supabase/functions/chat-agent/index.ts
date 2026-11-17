import { createClient } from "npm:@supabase/supabase-js@2";
import { corsHeaders, json } from "./cors.ts";
import { complete, llmConfig, type NMsg } from "./llm.ts";
import { execTool, TOOLS, type Ctx } from "./tools.ts";
import { summarizeFilm } from "./film.ts";

const MAX_STEPS = 10;
const HISTORY_LIMIT = 40;
const DEADLINE_MS = 120_000;
const HOURLY_LIMIT = Number(Deno.env.get("AGENT_HOURLY_LIMIT") ?? 60);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const SYSTEM = `Tu es l'agent central de GALINGTOSH, un studio audiovisuel piloté par la conversation.
L'utilisateur décrit ce qu'il veut produire (documentaire, fiction, court-métrage, clip, publicité, reportage, contenu éducatif, vidéo sociale, histoire à partir de photos, ou tout autre format). Tu construis et modifies le projet avec tes outils.

RÈGLES
- Tu ne modifies le film QUE par les outils. N'affirme jamais qu'une modification est faite si l'outil n'a pas retourné ok.
- Aucune génération d'images ou de vidéos par IA : tu cherches des médias existants, tu analyses les images fournies, tu utilises les imports de l'utilisateur, tu composes avec mouvements de caméra programmatiques, SVG, graphiques, transitions, voix off et sous-titres.
- Ne dis jamais qu'un média est « libre de droits » : cite sa licence, son auteur et ses restrictions tels que retournés par les outils (attribution obligatoire, usage non commercial, etc.).
- Pose une question uniquement si une information indispensable manque ; si l'intention est claire, propose et agis.
- Modifications ciblées : pour « rends la scène 2 plus dramatique », modifie seulement les éléments concernés, ne reconstruis pas le film.
- Recommande un format adapté (9:16 vertical réseaux sociaux, 16:9 documentaire/film, 1:1 ou 4:5 fil d'actualité, 21:9 cinéma).
- Le rendu est exécuté par un worker externe : après request_render, dis que le rendu est en file d'attente, pas que la vidéo est prête.
- Pour les histoires à partir de photos : construis le récit, décris les images nécessaires, demande-les à l'utilisateur, analyse-les (analyze_media), associe-les aux scènes, puis adapte le récit.
- N'identifie jamais une personne réelle à son visage.
- Réponds dans la langue de l'utilisateur (français par défaut), de façon concise et lisible sur mobile.`;

function toHistory(rows: any[]): NMsg[] {
  const clip = (s: string) => (s.length > 8000 ? s.slice(0, 8000) + "…[tronqué]" : s);
  const out: NMsg[] = [];
  let i = 0;
  while (i < rows.length) {
    const r = rows[i];
    if (r.role === "user") {
      const att = r.metadata?.attachments;
      const suffix = Array.isArray(att) && att.length
        ? `\n[Pièces jointes : ${att.map((a: any) => `${a.id} (${a.kind}${a.name ? ", " + a.name : ""})`).join("; ")}]` : "";
      out.push({ role: "user", content: r.content + suffix });
      i++;
    } else if (r.role === "assistant") {
      const calls = r.metadata?.tool_calls ?? [];
      if (!calls.length) {
        if (r.content) out.push({ role: "assistant", content: r.content });
        i++;
        continue;
      }
      let j = i + 1;
      const tools: any[] = [];
      while (j < rows.length && rows[j].role === "tool") { tools.push(rows[j]); j++; }
      const ids = new Set(tools.map((t) => t.metadata?.tool_call_id));
      if (calls.every((c: any) => ids.has(c.id))) {
        out.push({ role: "assistant", content: r.content, tool_calls: calls });
        for (const c of calls) {
          const t = tools.find((x) => x.metadata?.tool_call_id === c.id);
          out.push({ role: "tool", content: clip(t.content), tool_call_id: c.id, name: c.name, is_error: !!t.metadata?.is_error });
        }
      } // sinon : échange interrompu (appel sans résultat), on l'ignore
      i = j;
    } else i++;
  }
  while (out.length && out[0].role !== "user") out.shift();
  return out;
}

async function saveMsg(admin: any, conversationId: string, userId: string, role: string, content: string, metadata: Record<string, unknown> = {}) {
  const { error } = await admin.from("messages").insert({ conversation_id: conversationId, user_id: userId, role, content, metadata });
  if (error) throw new Error("Enregistrement du message impossible.");
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return json({ error: "Méthode non autorisée" }, 405);
  try {
    return await handle(req);
  } catch (e) {
    console.error(e);
    return json({ error: "La demande a été interrompue. Les opérations déjà enregistrées sont conservées. Rouvrez le projet avant de réessayer." }, 500);
  }
});

async function handle(req: Request): Promise<Response> {
  const started = Date.now();
  const token = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
  const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: u, error: ue } = await admin.auth.getUser(token);
  if (ue || !u?.user) return json({ error: "Non authentifié" }, 401);
  const userId = u.user.id;

  const body = await req.json().catch(() => null);
  const message = typeof body?.message === "string" ? body.message.trim() : "";
  if (!message || message.length > 8000) return json({ error: "message requis (1 à 8000 caractères)" }, 400);
  for (const k of ["conversation_id", "project_id"]) {
    if (body[k] !== undefined && body[k] !== null && (typeof body[k] !== "string" || !UUID.test(body[k]))) return json({ error: `${k} invalide` }, 400);
  }

  // Configuration du fournisseur IA (variables d'environnement, sinon base + Vault) : jamais de réponse simulée si elle manque.
  const { cfg, missing } = await llmConfig(admin);
  if (!cfg) {
    return json({
      code: "llm_not_configured",
      error: "L'agent IA n'est pas configuré sur ce projet (réglages ou clé manquants).",
      missing,
    }, 503);
  }

  cfg.deadlineAt = started + 110_000;

  // Limite horaire (contrôle des coûts)
  const since = new Date(Date.now() - 3600_000).toISOString();
  const { count } = await admin.from("usage_events").select("id", { count: "exact", head: true })
    .eq("user_id", userId).eq("kind", "agent_request").gte("created_at", since);
  if ((count ?? 0) >= HOURLY_LIMIT) {
    return json({ code: "rate_limited", error: "Limite horaire de requêtes atteinte. Réessaie plus tard." }, 429);
  }

  // Conversation
  let conversationId: string | null = body.conversation_id ?? null;
  let projectId: string | null = body.project_id ?? null;
  if (conversationId) {
    const { data: c } = await admin.from("conversations").select("id, project_id").eq("id", conversationId).eq("user_id", userId).maybeSingle();
    if (!c) return json({ error: "Conversation introuvable" }, 404);
    if (projectId && c.project_id !== projectId) return json({ error: "Cette conversation appartient à un autre projet. Rouvrez le projet souhaité." }, 409);
    projectId = c.project_id ?? null;
    if (projectId) {
      const { data: owned } = await admin.from("projects").select("id").eq("id",projectId).eq("user_id",userId).maybeSingle();
      if (!owned) return json({error:"Projet introuvable"},404);
    }
  } else {
    if (projectId) {
      const { data: p } = await admin.from("projects").select("id").eq("id", projectId).eq("user_id", userId).maybeSingle();
      if (!p) return json({ error: "Projet introuvable" }, 404);
    }
    const { data: c, error } = await admin.from("conversations")
      .insert({ user_id: userId, project_id: projectId, title: message.slice(0, 60) }).select("id").single();
    if (error) return json({ error: error.message }, 500);
    conversationId = c.id;
  }

  // Pièces jointes : des media_assets déjà importés par le client dans ce projet
  let attachments: any[] = [];
  if (Array.isArray(body.attachments) && body.attachments.length) {
    if (!projectId) return json({ error: "Les pièces jointes exigent un projet (project_id)" }, 400);
    if (body.attachments.length > 10 || body.attachments.some((x:unknown)=>typeof x !== "string" || !UUID.test(x))) return json({error:"Pièces jointes invalides (10 identifiants maximum)."},400);
    const ids = [...new Set(body.attachments)] as string[];
    const { data: rows } = await admin.from("media_assets").select("id, kind, storage_path")
      .in("id", ids).eq("project_id", projectId).eq("user_id", userId);
    if (!rows || rows.length !== ids.length) return json({error:"Un média joint est introuvable dans ce projet."},400);
    attachments = (rows ?? []).map((r: any) => ({ id: r.id, kind: r.kind, name: r.storage_path?.split("/").pop() }));
  }

  await admin.from("usage_events").insert({ user_id: userId, kind: "agent_request", units: 1 });
  await saveMsg(admin, conversationId!, userId, "user", message, attachments.length ? { attachments } : {});

  // Historique + état du film
  const { data: rows } = await admin.from("messages").select("role, content, metadata")
    .eq("conversation_id", conversationId).order("created_at", { ascending: false }).limit(HISTORY_LIMIT);
  const history = toHistory((rows ?? []).reverse());

  let state = "Aucun projet n'est encore lié à cette conversation : appelle create_project dès que l'utilisateur décrit une production.";
  if (projectId) {
    const { data: film } = await admin.from("films").select("data, version").eq("project_id", projectId)
      .order("version", { ascending: false }).limit(1).maybeSingle();
    if (film) state = `ÉTAT ACTUEL DU PROJET (version de travail ${film.version}) :\n${summarizeFilm(film.data)}`;
  }
  const system = `${SYSTEM}\n\n${state}`;

  const ctx: Ctx = { admin, userId, conversationId: conversationId!, projectId, cfg, usage: { input: 0, output: 0 } };
  const events: { tool: string; ok: boolean }[] = [];
  let reply = "";
  let renderJobId: string | null = null;

  try {
    for (let step = 0; step < MAX_STEPS; step++) {
      if (Date.now() - started > DEADLINE_MS) { reply = "Je n'ai pas pu terminer dans le temps imparti. Les opérations déjà appliquées sont conservées : redemande-moi la suite."; break; }
      const res = await complete(cfg, system, history, TOOLS);
      ctx.usage.input += res.usage.input; ctx.usage.output += res.usage.output;

      if (!res.toolCalls.length) { reply = res.text; break; }

      const calls = res.toolCalls.map((c, i) => ({ ...c, id: c.id || `call_${step}_${i}` }));
      history.push({ role: "assistant", content: res.text, tool_calls: calls });
      await saveMsg(admin, conversationId!, userId, "assistant", res.text, { tool_calls: calls });

      for (const c of calls) {
        const out = await execTool(ctx, c.name, c.args ?? {});
        events.push({ tool: c.name, ok: !out.isError });
        if (out.metadata?.kind === "render_job") renderJobId = out.metadata.job_id;
        const content = JSON.stringify(out.output);
        history.push({ role: "tool", content: content.length > 8000 ? content.slice(0, 8000) + "…[tronqué]" : content, tool_call_id: c.id, name: c.name, is_error: !!out.isError });
        await saveMsg(admin, conversationId!, userId, "tool", content, {
          tool_call_id: c.id, name: c.name, is_error: !!out.isError, ...(out.metadata ?? {}),
        });
      }
      if (step === MAX_STEPS - 1) reply = "J'ai atteint la limite d'étapes pour cette demande. Les opérations déjà appliquées sont conservées : dis-moi si je dois continuer.";
    }
  } finally {
    await admin.from("usage_events").insert({
      user_id: userId, kind: "llm_tokens", provider: `${cfg.provider}:${cfg.model}`,
      units: ctx.usage.input + ctx.usage.output, cost_usd: 0,
    });
  }

  if (!reply) reply = events.length ? `Opérations effectuées : ${events.map((e) => e.tool).join(", ")}.` : "Je n'ai pas de réponse à donner pour le moment.";
  await saveMsg(admin, conversationId!, userId, "assistant", reply);

  let filmVersion: number | null = null;
  if (ctx.projectId) {
    const { data: f } = await admin.from("films").select("version").eq("project_id", ctx.projectId)
      .order("version", { ascending: false }).limit(1).maybeSingle();
    filmVersion = f?.version ?? null;
  }
  return json({ reply, conversation_id: conversationId, project_id: ctx.projectId, film_version: filmVersion, render_job_id: renderJobId, tool_events: events });
}

