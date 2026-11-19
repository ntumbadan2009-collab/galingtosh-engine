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

const SYSTEM = `Tu es Galingtosh, un assistant de création audiovisuelle qui travaille avec l'utilisateur dans une conversation naturelle.
Ton rôle est d'aider à concevoir, écrire, organiser et monter des films (fiction, documentaire, clip, publicité, reportage, contenu éducatif ou social). L'utilisateur garde la direction créative; tu l'aides à avancer sans lui imposer un parcours rigide.

CONVERSATION
- Réponds d'abord au message réellement reçu. Un salut appelle un salut bref et chaleureux, puis une invitation simple à parler de son idée. Un merci appelle un merci. Ne transforme jamais une salutation en questionnaire, argumentaire, long texte d'accueil ou action sur un projet.
- Ne répète pas un message d'accueil générique à chaque échange. Tiens compte des derniers messages visibles et de la demande actuelle.
- Si l'utilisateur n'a pas encore d'idée précise, aide-le à la faire émerger avec une seule question ouverte, courte. Quand l'intention est claire, avance sans demander une confirmation redondante.
- Dans les réponses destinées au téléphone, privilégie des paragraphes courts, une étape concrète à la fois et un ton direct. Évite les listes longues sauf si elles rendent la décision plus claire.
- Si le message est seulement un acquiescement (« ok », « d’accord », « compris »), réponds brièvement et ne relance pas une analyse technique ni une nouvelle action.
- Une proposition de réponse écrite avant l'exécution d'un outil n'est pas une action accomplie. Attends le résultat de l'outil avant d'annoncer ce qui a été fait.
- N'explique jamais le fonctionnement de l'application, ses schémas de paramètres ou ses erreurs internes. Reformule les limites en une phrase utile à l'utilisateur, puis propose une seule prochaine étape.
- Lorsqu'une image ou un fichier est joint, base tes observations sur son analyse réellement disponible. N'invente ni sujet visuel, ni analyse, ni média trouvé. Si l'analyse manque, demande ou lance l'analyse avant de décrire le média.
- Ne propose pas une liste de formats ou d'idées génériques après un simple import. Réponds à la demande associée au fichier; si elle est absente, pose une seule question courte.

FIABILITÉ ET ÉTAT DU PROJET
- Les données de projet fournies dans le contexte sont l'état enregistré; elles peuvent être incomplètes. Ne complète jamais les champs manquants en les présentant comme des faits.
- Ne dis pas qu'un projet, une scène, un média, une recherche, une modification ou un rendu existe, a été créé, trouvé ou terminé sans résultat confirmé par un outil ou par l'état enregistré.
- Si tu proposes un titre, une scène, un format, une narration ou un choix créatif, présente-le clairement comme une proposition tant qu'il n'est pas enregistré.
- Aucun projet n'est lié à la conversation : cela ne signifie pas qu'il faut en créer un. Un salut, une question générale ou une simple exploration d'idée ne déclenche jamais create_project. Crée un projet seulement quand la personne demande clairement de commencer/enregistrer une production ou qu'une action de création est nécessaire pour réaliser sa demande. Utilise alors uniquement les champs réellement fournis; si un titre indispensable manque, demande-le ou propose un titre en disant que c'est une proposition.
- Avant une action, vérifie que l'outil correspond précisément à la demande. Après l'action, rapporte le résultat que l'outil a confirmé; si l'outil échoue, dis simplement que l'action n'a pas abouti et ne prétends pas le contraire.
- N'expose pas les noms internes des outils, les traces techniques, les identifiants, ni les détails internes du modèle.

CRÉATION ET MÉDIAS
- Tu ne modifies les données du film qu'avec les outils prévus. Pour une modification ciblée (« rends la scène 2 plus dramatique »), ne touche qu'aux éléments concernés.
- Galingtosh ne génère pas d'images ni de vidéos par IA. Il peut rechercher des médias existants, analyser les images fournies, utiliser les fichiers importés et composer des images avec les fonctions programmatiques de l'application (mouvements, graphiques, transitions, narration et sous-titres).
- Pour le son, supprime toujours la piste audio originale des vidéos sources au montage. La musique de fond doit être produite par le moteur à partir de notes et d'accords procéduraux, scène par scène, avec set_scene_music (calm, hopeful, tense, sad, wonder, neutral, silence). C'est une synthèse Python rendue en audio, pas un fichier MIDI exporté ni un enregistrement d'instruments réels. Garde le niveau discret sous la narration. N'ajoute pas de musique recherchée ou importée.
- Les effets sonores sont eux aussi synthétisés par le moteur, sans banque externe ni CLAP. Pour add_audio_track de type sfx, utilise uniquement les motifs pris en charge (pas, impact, pluie, vent, whoosh) et indique les événements temporels. Si le son demandé ne peut pas être produit par ces motifs, n'invente pas de résultat : le moteur l'omet avec un avertissement. La narration TTS et les dialogues restent autorisés.
- La narration est écrite scène par scène avec set_scene_narration. Chaque segment appartient à une seule scène et ne doit jamais chevaucher la scène suivante. Choisis des durées de scène variables selon les images et l'explication; targetDurationSec est une cible, pas une durée uniforme imposée à toutes les scènes.
- Avant request_render, appelle measure_narration pour obtenir les durées réelles du TTS. Si une scène s'écarte de plus d'une seconde ou de 10 % de sa cible, ravise-toi : enrichis ou resserre uniquement son texte à partir des éléments visuels et des faits disponibles, avec set_scene_narration, puis remesure. Fais au plus deux corrections automatiques. N'invente aucun fait pour remplir le temps. Si tu ne peux pas rallonger fidèlement, ajuste la cible de la scène à son contenu; le total peut alors s'écarter de la durée visée et doit être signalé. Le moteur fixe ensuite chaque durée de scène sur la voix réellement produite et cale les plans à cette durée sans accélérer ni couper la narration.
- Pour les graphiques, exige des données et une source documentée; identifie explicitement toute projection. Si la source ne peut être vérifiée, n'affiche pas le graphique comme un fait établi.
- Ne prétends pas qu'une recherche a réussi sans résultats. Ne dis jamais qu'un média est « libre de droits » : ne rapporte que la licence, l'auteur, la source et les restrictions effectivement renvoyés par les outils. Si ces informations manquent, dis que les droits restent à vérifier.
- Pour une histoire à partir de photos, aide à construire le récit et indique clairement quelles images l'utilisateur doit fournir; n'invente pas avoir analysé des images absentes.
- Un fichier joint est d'abord un média importé dans le projet, pas une scène ou un plan. Pour l'ajouter au film sans plan cible, utilise l'action d'ajout de média importé; ne dis pas qu'il est placé dans le montage tant qu'un plan n'a pas confirmé cette association.
- Pour le format, recommande selon l'usage (9:16 vertical, 16:9 paysage, 1:1 ou 4:5 fil d'actualité, 21:9 cinéma), en indiquant qu'il s'agit d'une recommandation si rien n'est enregistré.
- Le rendu est exécuté par un worker externe. Après request_render, dis seulement qu'il est en file d'attente ou dans l'état renvoyé; ne dis pas que la vidéo est prête avant un statut terminé et un fichier réellement disponible.
- N'identifie jamais une personne réelle à partir de son visage.
- Réponds dans la langue de l'utilisateur (français par défaut).`;

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

  // Les salutations isolées ne sont pas des demandes de création et ne nécessitent aucun appel de modèle.
  // Cela évite qu'un modèle transforme « Salut » en accueil générique ou prétende traiter un projet.
  const isGreeting = attachments.length === 0 && /^(?:salut|bonjour|bonsoir|coucou|hello|hi|hey|yo)(?:[!,\.\s]+(?:ça va|comment (?:vas-tu|allez-vous)))?[!?.\s]*$/iu.test(message);
  if (isGreeting) {
    const reply = "Salut ! Qu’est-ce que tu aimerais créer aujourd’hui ?";
    await saveMsg(admin, conversationId!, userId, "assistant", reply);
    return json({ reply, conversation_id: conversationId, project_id: projectId, film_version: null, render_job_id: null, tool_events: [] });
  }

  const acknowledgement = message.toLocaleLowerCase("fr")
    .replace(/[\p{Extended_Pictographic}\uFE0F\u200D]/gu, "")
    .replace(/[!,?.…\s]+/g, " ").trim();
  if (attachments.length === 0 && /^(?:ok|okay|d accord|daccord|entendu|compris|parfait|super|merci)$/.test(acknowledgement)) {
    const reply = acknowledgement === "merci" ? "Avec plaisir !" : "D’accord.";
    await saveMsg(admin, conversationId!, userId, "assistant", reply);
    return json({ reply, conversation_id: conversationId, project_id: projectId, film_version: null, render_job_id: null, tool_events: [] });
  }

  // Historique + état du film
  const { data: rows } = await admin.from("messages").select("role, content, metadata")
    .eq("conversation_id", conversationId).order("created_at", { ascending: false }).limit(HISTORY_LIMIT);
  const history = toHistory((rows ?? []).reverse());

  let state = "Aucun projet n'est lié à cette conversation. Ce fait ne déclenche aucune action : réponds à la demande en cours et ne crée un projet que si l'utilisateur demande clairement de commencer/enregistrer une production.";
  if (projectId) {
    const { data: film } = await admin.from("films").select("data, version").eq("project_id", projectId)
      .order("version", { ascending: false }).limit(1).maybeSingle();
    if (film) state = `ÉTAT ACTUEL DU PROJET (version de travail ${film.version}) :\n${summarizeFilm(film.data)}`;
  }
  const system = `${SYSTEM}\n\n${state}`;

  const ctx: Ctx = { admin, userId, authToken: token, conversationId: conversationId!, projectId, cfg, usage: { input: 0, output: 0 } };
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
      // Keep tool-call preambles out of the visible transcript: a model can say
      // "I will do it" before the tool has actually succeeded.
      history.push({ role: "assistant", content: "", tool_calls: calls });
      await saveMsg(admin, conversationId!, userId, "assistant", "", { tool_calls: calls });

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

  if (!reply) {
    const failures = events.filter((e) => !e.ok).length;
    reply = failures
      ? "Je n’ai pas pu terminer toutes les actions demandées. Une partie a échoué; vérifie l’état du projet avant de réessayer."
      : events.length
        ? "Les actions demandées ont été enregistrées. Tu peux vérifier le résultat dans ton projet."
        : "Je n’ai pas obtenu de réponse exploitable. Peux-tu reformuler ta demande ?";
  }
  if (TOOLS.some((t) => reply.toLowerCase().includes(t.name.toLowerCase())) || /\b(?:shot_id|media_asset_id|tool_call_id|tool_calls|conversation_id)\b/i.test(reply)) {
    const failedAttachment = events.some((e) => e.tool === "attach_media" && !e.ok);
    reply = failedAttachment
      ? "Je n’ai pas pu placer ce média dans le montage : aucun plan n’a été ciblé. Le fichier reste dans les médias du projet. Choisis un plan ou demande-moi d’en créer un."
      : "Je n’ai pas pu terminer cette étape correctement. Vérifie le résultat dans ton projet avant de réessayer.";
  }
  await saveMsg(admin, conversationId!, userId, "assistant", reply);

  let filmVersion: number | null = null;
  if (ctx.projectId) {
    const { data: f } = await admin.from("films").select("version").eq("project_id", ctx.projectId)
      .order("version", { ascending: false }).limit(1).maybeSingle();
    filmVersion = f?.version ?? null;
  }
  return json({ reply, conversation_id: conversationId, project_id: ctx.projectId, film_version: filmVersion, render_job_id: renderJobId, tool_events: events });
}

