import { createClient } from "npm:@supabase/supabase-js@2";
import { corsHeaders, json } from "./cors.ts";
import { complete, llmConfig, type NMsg } from "./llm.ts";
import { execTool, TOOLS, type Ctx } from "./tools.ts";
import { summarizeFilm } from "./film.ts";
import {verifyPrecisionRevision} from "./precision_revision.ts";
import {PROPOSAL_TOOL,proposeMission,approveMission,productionTick} from "./production.ts";
import {interpretPlanReply} from "./proposal-intents.ts";

// Wake the render service once in response to a real queued workload.
// This is dispatch, not a periodic keep-alive. A failed wake leaves the mission intact.
declare const EdgeRuntime: { waitUntil(promise: Promise<unknown>): void };
function dispatchProduction():void {
  const engine=(Deno.env.get("RENDER_ENGINE_URL")??"https://galingtosh-engine.onrender.com").replace(/\/$/,"");
  EdgeRuntime.waitUntil((async()=>{
    try{
      const response=await fetch(engine+"/",{signal:AbortSignal.timeout(120_000)});
      await response.body?.cancel();
      if(!response.ok)console.warn("Production en file; moteur momentanément indisponible",response.status);
    }catch{console.warn("Production en file; réveil du moteur non confirmé.");}
  })());
}

const MAX_STEPS = 10;
const HISTORY_LIMIT = 40;
// Keep time to persist a clear response even when the model provider times out.
const DEADLINE_MS = 43_000;
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
- Pour sélectionner un extrait d'une vidéo existante, commence par examiner les passages disponibles avec inspect_video_clips lorsque l'analyse est accessible. Ces intervalles sont calculés à partir des changements visuels : ils NE prouvent PAS le sujet ni l'action montrés. Ne prétends jamais avoir vu ou compris le passage si aucune analyse visuelle réelle n'a été effectuée. Le champ sourceInSec du plan détermine le début dans la vidéo source; inSec et outSec déterminent sa position dans la scène. Ne confonds jamais les deux. Ne choisis pas un extrait au hasard lorsque sa pertinence doit être vérifiée.
- Galingtosh ne génère pas d'images ni de vidéos par IA. Il peut rechercher des médias existants, analyser les images fournies, utiliser les fichiers importés et composer des images avec les fonctions programmatiques de l'application (mouvements, graphiques, transitions, narration et sous-titres).
- NIVEAU 2 DES VISUELS : préfère des schémas animés créés par code lorsque les archives ne montrent pas INTUITIVEMENT la narration. L'outil add_code_shot accepte visualType=focus|steps|timeline|comparison|cause_effect|cube_rotation|sphere_rotation et visualItems (citations exactes, ordonnées, de visualText) pour déclencher des révélations graphiques progressives sans aucune génération IA. Timeline UNIQUEMENT si le récit exprime un ordre temporel; comparison UNIQUEMENT s'il exprime un contraste. Aucun tableau chiffré, événement, date, lieu ou causalité ne peut être inventé pour décorer. set_motion_visual permet de perfectionner un plan code déjà ajouté. Un média recherché reste interdit dans un plan autonome tant que la vision réelle n'a pas confirmé sa pertinence.
- Pour le son, supprime toujours la piste audio originale des vidéos sources au montage. La musique de fond doit être produite par le moteur à partir de notes et d'accords procéduraux, scène par scène, avec set_scene_music (calm, hopeful, tense, sad, wonder, neutral, silence). C'est une synthèse Python rendue en audio, pas un fichier MIDI exporté ni un enregistrement d'instruments réels. Garde le niveau discret sous la narration. N'ajoute pas de musique recherchée ou importée.
- Les effets sonores peuvent provenir d'un véritable extrait audio public CC0/CC BY vérifié par verify_and_add_sound (analyse du son réel et empreinte contrôlée au rendu, lorsque le fournisseur audio est compatible), ou être synthétisés localement. Ne prétends pas disposer d'une banque complète ni d'une écoute si le fournisseur ne la confirme pas. Pour add_audio_track de type sfx, utilise uniquement les motifs pris en charge (pas, impact, pluie, vent, whoosh) et indique les événements temporels. Si le son demandé ne peut pas être produit par ces motifs, n'invente pas de résultat : le moteur l'omet avec un avertissement. La narration TTS et les dialogues restent autorisés.
- La narration est écrite scène par scène avec set_scene_narration, qui permet un débit et une hauteur bornés. Pour les documentaires, reportages et contenus éducatifs de niveau 5, review_documentary_scene examine les véritables extraits sources; les affirmations insuffisamment étayées doivent être corrigées et revérifiées. Chaque segment appartient à une seule scène et ne doit jamais chevaucher la scène suivante. Choisis des durées de scène variables selon les images et l'explication; targetDurationSec est une cible, pas une durée uniforme imposée à toutes les scènes.
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
  const body = await req.json().catch(() => null);
  if(body?.action==="production_tick"){
    const secret=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")??"";
    if(!secret||token!==secret)return json({error:"Non autorisé"},403);
    return json(await productionTick(admin,token,SYSTEM));
  }
  const { data: u, error: ue } = await admin.auth.getUser(token);
  if (ue || !u?.user) return json({ error: "Non authentifié" }, 401);
  const userId = u.user.id;
  // Explicit authenticated client action, not a model-callable mutation.
  if(body?.action==="apply_precision_revision"){
    const {projectId,filmId,version,rev,edits,sourceHash,candidateHash}=body;
    if(![projectId,filmId].every(x=>typeof x==="string"&&UUID.test(x))||
      !Number.isSafeInteger(version)||!Number.isSafeInteger(rev)||
      ![sourceHash,candidateHash].every(x=>typeof x==="string"&&/^[0-9a-f]{64}$/.test(x)))
      return json({error:"Révision invalide."},400);
    const {data:owned,error:ownerError}=await admin.from("projects").select("id").eq("id",projectId).eq("user_id",userId).maybeSingle();
    if(ownerError||!owned)return json({error:"Projet introuvable."},404);
    const {data:mission,error:missionError}=await admin.from("production_missions").select("id")
      .eq("project_id",projectId).eq("user_id",userId).not("status","in","(done,failed,canceled,needs_review)").limit(1).maybeSingle();
    if(missionError||mission)return json({error:"Révision indisponible pendant une production active."},409);
    const {data:row,error:loadError}=await admin.from("films").select("id,data,version,rev")
      .eq("project_id",projectId).eq("user_id",userId).order("version",{ascending:false}).limit(1).maybeSingle();
    if(loadError||!row||row.id!==filmId||row.version!==version||row.rev!==rev)
      return json({error:"Version de travail modifiée. Recrée la prévisualisation."},409);
    try{
      const p=await verifyPrecisionRevision(row.data,edits,sourceHash,candidateHash);
      const {data:saved,error:saveError}=await admin.rpc("save_film_operation",{
        p_user_id:userId,p_film_id:row.id,p_rev:row.rev,p_data:p.candidate,
        p_op:{name:"precision_revision",args:{edits:p.receipt.edits,sourceHash,candidateHash}}
      });
      if(saveError||!saved)return json({error:"Révision non enregistrée; recharge le film."},409);
      return json({ok:true,applied:true,filmId,version,changes:p.receipt.changes,renderRequested:false});
    }catch{return json({error:"Révision refusée ou prévisualisation obsolète."},409);}
  }
  if(body?.action==="approve_production"||body?.action==="control_production"){
    const missionId=body.mission_id;
    if(typeof missionId!=="string"||!UUID.test(missionId))return json({error:"Mission invalide"},400);
    const {data:mission,error:missionError}=await admin.from("production_missions").select("id,status,conversation_id,project_id").eq("id",missionId).eq("user_id",userId).maybeSingle();
    if(missionError||!mission)return json({error:"Mission introuvable"},404);
    try{
      let reply: string | undefined;
      if(body.action==="approve_production"){
        await approveMission(admin,userId,mission.conversation_id,mission.id);
        if(mission.status==="draft"){
          reply="Plan validé. La production est lancée côté serveur ; tu peux suivre les étapes dans le Studio.";
          await saveMsg(admin,mission.conversation_id,userId,"user","Je valide le plan",{production_mission_id:mission.id});
          await saveMsg(admin,mission.conversation_id,userId,"assistant",reply,{production_mission_id:mission.id});
        }
        dispatchProduction();
      }else{
        if(!["pause","resume","cancel"].includes(body.command))return json({error:"Commande invalide"},400);
        const {error}=await admin.rpc("control_production",{p_mission_id:mission.id,p_user_id:userId,p_action:body.command});
        if(error)throw Error("Commande impossible dans cet état.");
        if(body.command==="resume")dispatchProduction();
        if(body.command==="cancel"&&mission.status==="draft"){
          reply="Le plan a été refusé. Tu peux décrire un autre projet ou demander une nouvelle proposition.";
          await saveMsg(admin,mission.conversation_id,userId,"user","Je refuse ce plan",{production_mission_id:mission.id});
          await saveMsg(admin,mission.conversation_id,userId,"assistant",reply,{production_mission_id:mission.id});
        }
      }
      return json({ok:true,production_mission_id:mission.id,reply});
    }catch{return json({error:"Cette commande est indisponible pour le moment."},409);}
  }

  const message = typeof body?.message === "string" ? body.message.trim() : "";
  if (!message || message.length > 8000) return json({ error: "message requis (1 à 8000 caractères)" }, 400);
  for (const k of ["conversation_id", "project_id"]) {
    if (body[k] !== undefined && body[k] !== null && (typeof body[k] !== "string" || !UUID.test(body[k]))) return json({ error: `${k} invalide` }, 400);
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

  // An "OK" only approves a draft owned by this exact user/project/conversation.
  // A compound reply ("OK mais...") is always handled as a revision, not consent.
  let pendingDraft: {id:string;goal:string;plan:string;target_seconds:number}|null=null;
  if(conversationId&&projectId){
    const {data,error}=await admin.from("production_missions")
      .select("id,goal,plan,target_seconds").eq("user_id",userId).eq("project_id",projectId)
      .eq("conversation_id",conversationId).eq("status","draft")
      .order("created_at",{ascending:false}).limit(1).maybeSingle();
    if(error)return json({error:"Impossible de vérifier la proposition en attente."},503);
    pendingDraft=data;
  }
  const planReply=Array.isArray(body.attachments)&&body.attachments.length?null:interpretPlanReply(message);
  if(pendingDraft&&planReply){
    const missionId=pendingDraft.id;
    if(planReply==="approve"){
      await approveMission(admin,userId,conversationId!,missionId);
      dispatchProduction();
    }else{
      const {error}=await admin.rpc("control_production",{
        p_mission_id:missionId,p_user_id:userId,p_action:"cancel"
      });
      if(error)return json({error:"Ce plan ne peut plus être annulé."},409);
    }
    const reply=planReply==="approve"
      ?"Plan validé. La production est lancée côté serveur ; tu peux suivre les étapes dans le Studio."
      :"Le plan a été refusé. Tu peux décrire un autre projet ou demander une nouvelle proposition.";
    await saveMsg(admin,conversationId!,userId,"user",message,{production_mission_id:missionId});
    await saveMsg(admin,conversationId!,userId,"assistant",reply,{production_mission_id:missionId});
    return json({reply,conversation_id:conversationId,project_id:projectId,production_mission_id:missionId,tool_events:[]});
  }
  if(projectId){
    const {data:active}=await admin.from("production_missions").select("id,status").eq("project_id",projectId).eq("user_id",userId)
      .in("status",["queued","running","waiting_render","paused","needs_review"]).limit(1).maybeSingle();
    if(active){
      const reply=active.status==="needs_review"?"Cette production nécessite une vérification avant de pouvoir reprendre. Le montage est conservé.":"Une production est déjà active sur ce projet. Consulte son activité avant d’envoyer une nouvelle modification.";
      await saveMsg(admin,conversationId!,userId,"user",message);
      await saveMsg(admin,conversationId!,userId,"assistant",reply,{production_mission_id:active.id});
      return json({reply,conversation_id:conversationId,project_id:projectId,production_mission_id:active.id,tool_events:[]});
    }
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

  // Model calls must stop before the function runtime is forced to terminate.
  cfg.deadlineAt = started + 52_000;

  // Limite horaire (contrôle des coûts)
  const since = new Date(Date.now() - 3600_000).toISOString();
  const { count } = await admin.from("usage_events").select("id", { count: "exact", head: true })
    .eq("user_id", userId).eq("kind", "agent_request").gte("created_at", since);
  if ((count ?? 0) >= HOURLY_LIMIT) {
    return json({ code: "rate_limited", error: "Limite horaire de requêtes atteinte. Réessaie plus tard." }, 429);
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
  const draftContext=pendingDraft
    ? `\nPROPOSITION CRÉATIVE EN ATTENTE (NON APPROUVÉE). Objectif original : ${pendingDraft.goal}. Durée cible actuelle : ${pendingDraft.target_seconds} secondes. Proposition actuelle :\n${pendingDraft.plan}\nL'utilisateur peut donner des modifications libres dans le chat. S'il demande un ajustement, appelle UNIQUEMENT propose_production en conservant l'objectif original et les autres éléments non concernés. Ne touche PAS au Film JSON ou aux médias avant validation. Si l'utilisateur pose une question, réponds normalement sans modifier le plan. La réponse courte OK est traitée séparément et n'arrive pas au modèle.`
    : "";
  const system = `${SYSTEM}\n\n${state}\nPRODUCTION LONGUE OU COMPLÈTE : si l'utilisateur demande une nouvelle vidéo, un documentaire, un film ou une production complète, propose d'abord une direction créative et une durée. Ne demande que les précisions essentielles, groupées. Crée au besoin uniquement le projet vide, puis utilise propose_production pour enregistrer le plan complet. N'ajoute aucune scène, média ou narration avant son approbation explicite. Pour une modification locale d’un schéma animé existant, propose preview_precision_revision. Cette prévisualisation n’enregistre rien : ne prétends jamais que la révision a été appliquée. Les autres modifications locales conservent le comportement normal. La capacité actuelle reste limitée à 600 secondes et 45 Mo ; n'annonce pas une capacité supérieure.${draftContext}`;
  const availableTools=pendingDraft?[PROPOSAL_TOOL]:[...TOOLS,PROPOSAL_TOOL];

  const ctx: Ctx = { admin, userId, authToken: token, conversationId: conversationId!, projectId, cfg, usage: { input: 0, output: 0 } };
  const events: { tool: string; ok: boolean }[] = [];
  let reply = "";
  let renderJobId: string | null = null;
  let proposalId: string | null = null;

  try {
    for (let step = 0; step < MAX_STEPS; step++) {
      if (Date.now() - started > DEADLINE_MS) {
        reply = "J'ai enregistré les modifications déjà réalisées. Il reste des étapes à terminer : écris « Continue » dans ce projet pour reprendre sans recommencer.";
        break;
      }
      let res: Awaited<ReturnType<typeof complete>>;
      try {
        res = await complete(cfg, system, history, availableTools);
      } catch (e) {
        // Gemini rotation/provider timeouts are not film failures. Make sure
        // the client receives a durable, recoverable response rather than 500.
        console.warn("Agent LLM temporarily unavailable:", e instanceof Error ? e.message.slice(0, 350) : String(e));
        reply = events.length
          ? "Les modifications déjà effectuées sont enregistrées. La connexion au modèle IA a été interrompue avant la fin. Écris « Continue » pour reprendre les étapes restantes."
          : "Le modèle IA ne répond pas pour le moment. Ton projet est conservé ; réessaie la demande dans ce projet.";
        break;
      }
      ctx.usage.input += res.usage.input; ctx.usage.output += res.usage.output;

      if (!res.toolCalls.length) { reply = res.text; break; }

      // A proposal ends the turn; no other tool may mutate the film in that batch.
      const proposal=res.toolCalls.find(c=>c.name==="propose_production");
      if(proposal&&ctx.projectId){
        const p=await proposeMission(ctx,pendingDraft?.goal??message,proposal.args??{});
        proposalId=p.id;
        reply="J’ai préparé une direction créative pour une vidéo de "+p.duration+" secondes. Ouvre la fiche de proposition pour consulter les détails, touche « Valider et produire », écris « OK » dans le chat, ou demande-moi des modifications.";
        break;
      }
      const calls = res.toolCalls.filter(c=>c.name!=="propose_production").map((c, i) => ({ ...c, id: c.id || `call_${step}_${i}` }));
      if(!calls.length){reply=pendingDraft?"Précise les changements souhaités dans la proposition. Le plan actuel reste enregistré.":"Je dois d’abord associer cette proposition à un projet. Donne-moi son titre ou précise ton idée.";break;}
      // Keep tool-call preambles out of the visible transcript: a model can say
      // "I will do it" before the tool has actually succeeded.
      history.push({ role: "assistant", content: "", tool_calls: calls });
      await saveMsg(admin, conversationId!, userId, "assistant", "", { tool_calls: calls });

      for (const c of calls) {
        // Individual mutations are committed, so stop scheduling further
        // operations once the response budget is nearly consumed.
        if (Date.now() - started > DEADLINE_MS) {
          reply = "Les modifications réalisées sont conservées. La demande nécessite plusieurs étapes : écris « Continue » pour terminer la suite.";
          break;
        }
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
  if (!proposalId && (TOOLS.some((t) => reply.toLowerCase().includes(t.name.toLowerCase())) || /\b(?:shot_id|media_asset_id|tool_call_id|tool_calls|conversation_id)\b/i.test(reply))) {
    const failedAttachment = events.some((e) => e.tool === "attach_media" && !e.ok);
    reply = failedAttachment
      ? "Je n’ai pas pu placer ce média dans le montage : aucun plan n’a été ciblé. Le fichier reste dans les médias du projet. Choisis un plan ou demande-moi d’en créer un."
      : "Je n’ai pas pu terminer cette étape correctement. Vérifie le résultat dans ton projet avant de réessayer.";
  }
  await saveMsg(admin, conversationId!, userId, "assistant", reply,proposalId?{production_proposal_id:proposalId}:{});

  let filmVersion: number | null = null;
  if (ctx.projectId) {
    const { data: f } = await admin.from("films").select("version").eq("project_id", ctx.projectId)
      .order("version", { ascending: false }).limit(1).maybeSingle();
    filmVersion = f?.version ?? null;
  }
  return json({ reply, conversation_id: conversationId, project_id: ctx.projectId, film_version: filmVersion, render_job_id: renderJobId, tool_events: events });
}

