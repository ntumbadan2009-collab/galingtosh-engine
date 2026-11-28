// Interface commune aux fournisseurs de modèles : on change de modèle sans reconstruire l'application.
// Source de configuration (par clé, les variables d'environnement l'emportent) :
//   1. variables d'environnement : LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, LLM_BASE_URL, LLM_REASONING_EFFORT
//   2. sinon la base : table app_settings (réglages) + Vault (clé API) via la fonction get_llm_settings()
// LLM_PROVIDER : anthropic | openai (openai = tout service compatible /chat/completions, dont Groq et Gemini).
// Gemini : rotation cyclique automatique entre de nombreux modèles (voir GEMINI_POOL / GEMINI_RESERVE). Chaque modèle a son
// propre quota : sur erreur (429, 5xx, modèle absent, délai dépassé…) on passe au suivant, et l'erreur n'est renvoyée
// que si TOUS les modèles ont échoué. LLM_FALLBACK_MODELS (liste séparée par des virgules) remplace le groupe principal.
import type { Json } from "./film.ts";

export interface ToolDef { name: string; description: string; input_schema: Json }
// extra : métadonnées du fournisseur à renvoyer telles quelles (Gemini 3 : thought_signature).
export interface ToolCall { id: string; name: string; args: Json; extra?: Json }
export interface NMsg {
  role: "user" | "assistant" | "tool";
  content: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
  is_error?: boolean;
}
export interface LlmResult { text: string; toolCalls: ToolCall[]; usage: { input: number; output: number } }
export type LlmCfg = {
  provider: "anthropic" | "openai";
  model: string;
  key: string;
  base: string;
  reasoningEffort?: string;
  deadlineAt?: number;
};

let settingsCache: { at: number; s: Record<string, string> } | null = null;

async function dbSettings(admin: any): Promise<Record<string, string>> {
  if (settingsCache && Date.now() - settingsCache.at < 60_000) return settingsCache.s;
  const { data, error } = await admin.rpc("get_llm_settings");
  if (error || !data) return {};
  settingsCache = { at: Date.now(), s: data as Record<string, string> };
  return settingsCache.s;
}

export async function llmConfig(admin: any): Promise<{ cfg?: LlmCfg; missing?: string[] }> {
  const env = (k: string) => Deno.env.get(k) ?? "";
  const needDb = !(env("LLM_PROVIDER") && env("LLM_MODEL") && env("LLM_API_KEY"));
  const s = needDb ? await dbSettings(admin) : {};
  const provider = (env("LLM_PROVIDER") || s.llm_provider || "").toLowerCase();
  const model = env("LLM_MODEL") || s.llm_model || "";
  const key = env("LLM_API_KEY") || s.llm_api_key || "";
  const missing: string[] = [];
  if (provider !== "anthropic" && provider !== "openai") missing.push("llm_provider (anthropic ou openai)");
  if (!model) missing.push("llm_model");
  if (!key) missing.push("llm_api_key");
  if (missing.length) return { missing };
  const base = (env("LLM_BASE_URL") || s.llm_base_url ||
    (provider === "anthropic" ? "https://api.anthropic.com" : "https://api.openai.com/v1")).replace(/\/$/, "");
  const reasoningEffort = env("LLM_REASONING_EFFORT") || s.llm_reasoning_effort || undefined;
  return { cfg: { provider: provider as "anthropic" | "openai", model, key, base, reasoningEffort } };
}

async function post(url: string, headers: Record<string, string>, body: unknown, timeoutMs = 90_000) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!r.ok) throw new HttpError(r.status, (await r.text()).slice(0, 600));
  return r.json();
}

class HttpError extends Error {
  constructor(public status: number, public body: string) {
    super(`Fournisseur IA : HTTP ${status} ${body}`);
  }
}

// Asset-specific HTTP 400 errors cannot be repaired by switching models.
export function mediaInputFailure(status:number,body:string):boolean {
 return status===400&&/cannot fetch content from the provided url|failed to fetch (?:the )?(?:image|url)|invalid image (?:url|data)|unsupported image (?:format|mime)|image.*(?:could not be downloaded|not accessible)/i.test(body);
}
// --- Rotation cyclique Gemini -------------------------------------------------------------
// Deux niveaux : le « groupe principal » (modèles légers et rapides) tourne en cycle, une requête après l'autre ;
// la « réserve » (plus lente, plus lourde ou en préversion) n'est utilisée que si tout le groupe principal est indisponible.
// Retirés après constat dans les journaux : gemini-2.5-* (HTTP 404 : plus disponibles pour les nouveaux comptes).
const GEMINI_POOL = [
  "gemini-3.5-flash-lite",
  "gemini-3.1-flash-lite",
  "gemini-flash-lite-latest",
  "gemini-3.5-flash",
  "gemini-3.6-flash",
];
const GEMINI_RESERVE = [
  "gemini-3.7-flash",
  "gemini-3.8-flash",
  "gemini-3-flash-preview",
  "gemini-flash-latest",
  "gemini-3.1-pro-preview",
  "gemini-4-argon",
];
const GEMINI_BASE = /generativelanguage\.googleapis\.com/;
const ROTATION_BUDGET_MS = 35_000; // reste sous la limite de temps de la fonction
const ATTEMPT_TIMEOUT_MS = 13_000; // un modèle qui ne répond pas en 22 s est abandonné pour passer au suivant
const cooldown = new Map<string, number>(); // modèle -> instant (ms) avant lequel on l'évite
let cursor = 0; // prochain point de départ dans le groupe principal (persiste tant que l'instance est chaude)

function rotationPlan(cfg: LlmCfg): { pool: string[]; reserve: string[] } {
  const envList = (Deno.env.get("LLM_FALLBACK_MODELS") ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  const pool = envList.length ? [...envList] : [...GEMINI_POOL];
  const reserve = envList.length ? [] : [...GEMINI_RESERVE];
  if (cfg.model && !pool.includes(cfg.model) && !reserve.includes(cfg.model)) reserve.push(cfg.model);
  return { pool, reserve };
}

// Durée pendant laquelle un modèle en échec est mis de côté (0 = pas de mise à l'écart).
function cooldownFor(e: unknown): number {
  if (!(e instanceof HttpError)) {
    return (e as any)?.name === "TimeoutError" ? 3 * 60_000 : 20_000; // trop lent : 3 min ; réseau : 20 s
  }
  if (e.status === 429) {
    if (/per ?day/i.test(e.body)) return 30 * 60_000; // quota journalier épuisé
    const m = e.body.match(/"retryDelay":\s*"(\d+(?:\.\d+)?)s"/);
    return m ? Math.min(Math.ceil(Number(m[1]) * 1000) + 1000, 10 * 60_000) : 60_000;
  }
  if (e.status === 404) return 6 * 3600_000; // modèle inexistant ou fermé aux nouveaux comptes
  if (e.status === 401 || e.status === 403) return 10 * 60_000;
  if (e.status >= 500) return 15_000;
  return 0; // 400 & co : peut venir de la requête elle-même, on tourne sans bloquer le modèle
}

// Un seul appel /chat/completions compatible OpenAI (Groq, Gemini inclus) pour un modèle donné.
// - max_completion_tokens pour OpenAI/Groq (les modèles de raisonnement y comptent leur réflexion)
// - reasoning_effort envoyé si configuré ; si le fournisseur le refuse (HTTP 400), on réessaie sans.
function budget(cfg:LlmCfg, requested=90000):number {
  const left=Math.min(requested,(cfg.deadlineAt ?? Date.now()+requested)-Date.now());
  if(left<1000)throw new Error("Temps de traitement écoulé. Les modifications enregistrées sont conservées.");
  return left;
}
async function openaiChatOnce(cfg: LlmCfg, model: string, payload: Json, timeoutMs = 90_000): Promise<any> {
  const useCompletionTokens = /groq\.com|api\.openai\.com/.test(cfg.base);
  const { max_tokens, ...rest } = payload;
  const base: Json = { ...rest, model, [useCompletionTokens ? "max_completion_tokens" : "max_tokens"]: max_tokens };
  const headers = { Authorization: `Bearer ${cfg.key}` };
  const url = `${cfg.base}/chat/completions`;
  if (cfg.reasoningEffort) {
    try {
      return await post(url, headers, { ...base, reasoning_effort: cfg.reasoningEffort }, budget(cfg,timeoutMs));
    } catch (e) {
      if (!(e instanceof HttpError && e.status === 400 && /reasoning|thinking/i.test(e.body))) throw e;
    }
  }
  return await post(url, headers, base, budget(cfg,timeoutMs));
}

async function openaiChat(cfg: LlmCfg, payload: Json): Promise<any> {
  if (!GEMINI_BASE.test(cfg.base)) return await openaiChatOnce(cfg, cfg.model, payload);

  const { pool, reserve } = rotationPlan(cfg);
  const n = pool.length;
  const start = n ? cursor % n : 0;
  const cyclic: string[] = [];
  for (let i = 0; i < n; i++) cyclic.push(pool[(start + i) % n]); // groupe principal en cycle
  const now = Date.now();
  const ready = (m: string) => (cooldown.get(m) ?? 0) <= now;
  let attempts = [...cyclic.filter(ready), ...reserve.filter(ready)];
  if (!attempts.length) throw new Error("provider_cooldown: all Gemini models temporarily unavailable");

  const started = Date.now();
  const errors: string[] = [];
  let rateLimited=0,temporary=0;
  for (const model of attempts) {
    const left = Math.min(ROTATION_BUDGET_MS - (Date.now() - started),(cfg.deadlineAt ?? Infinity)-Date.now());
    if (left < 5_000) { errors.push("délai de rotation dépassé"); break; }
    try {
      const j = await openaiChatOnce(cfg, model, payload, Math.min(ATTEMPT_TIMEOUT_MS, left));
      // A successful HTTP response is not enough when an autonomous action is required.
      if(payload.tool_choice==="required"){
        const calls=j.choices?.[0]?.message?.tool_calls??j.choices?.[0]?.message?.toolCalls??[];
        const valid=Array.isArray(calls)&&calls.some((c:any)=>{
          if(!payload.tools?.some((t:any)=>t.function?.name===c.function?.name))return false;
          try{const a=typeof c.function.arguments==="string"?JSON.parse(c.function.arguments):c.function.arguments;return !!a&&typeof a==="object"&&!Array.isArray(a);}catch{return false;}
        });
        if(!valid)throw Error("Gemini: aucune action valide sélectionnée");
      }
      const pi = pool.indexOf(model);
      if (pi >= 0) cursor = (pi + 1) % n; // la prochaine requête démarre au modèle suivant du groupe principal
      cfg.model = model; // journalisation d'usage : modèle réellement utilisé
      return j;
    } catch (e) {
      if(e instanceof HttpError&&mediaInputFailure(e.status,e.body))throw Error("media_input_unavailable: provider cannot decode or fetch image");
      if(e instanceof HttpError&&e.status===429)rateLimited++;
      else if((e instanceof HttpError&&e.status>=500)||/timeout|timed out|abort/i.test(String(e)))temporary++;
      const cd = cooldownFor(e);
      if (cd) cooldown.set(model, Date.now() + cd);
      const msg = e instanceof Error ? e.message : String(e);
      console.warn(`Gemini ${model} indisponible, modèle suivant : ${msg.slice(0, 160)}`);
      errors.push(`${model} : ${msg.replace(/^Fournisseur IA : /, "").slice(0, 140)}`);
    }
  }
  throw new Error(`${rateLimited?"provider_rate_limited: ":temporary?"provider_temporarily_unavailable: ":""}Tous les modèles Gemini ont échoué (${errors.length}). ${errors.join(" | ")}`.slice(0, 1200));
}

// Retire les blocs de réflexion éventuellement renvoyés dans le contenu (modèles de réflexion).
const cleanText = (t: string | null | undefined) =>
  (t ?? "").replace(/<think>[\s\S]*?<\/think>/g, "").trim();

export async function complete(
  cfg: LlmCfg, system: string, messages: NMsg[], tools: ToolDef[], maxTokens = 8192, requireAction = false,
): Promise<LlmResult> {
  if (cfg.provider === "anthropic") {
    const msgs: any[] = [];
    for (const m of messages) {
      if (m.role === "user") {
        msgs.push({ role: "user", content: m.content });
      } else if (m.role === "assistant") {
        const blocks: any[] = [];
        if (m.content) blocks.push({ type: "text", text: m.content });
        for (const tc of m.tool_calls ?? []) blocks.push({ type: "tool_use", id: tc.id, name: tc.name, input: tc.args });
        msgs.push({ role: "assistant", content: blocks.length ? blocks : [{ type: "text", text: "…" }] });
      } else {
        const block = { type: "tool_result", tool_use_id: m.tool_call_id, content: m.content, is_error: !!m.is_error };
        const last = msgs[msgs.length - 1];
        if (last?.role === "user" && Array.isArray(last.content) && last.content[0]?.type === "tool_result") last.content.push(block);
        else msgs.push({ role: "user", content: [block] });
      }
    }
    const j = await post(`${cfg.base}/v1/messages`, { "x-api-key": cfg.key, "anthropic-version": "2023-06-01" }, {
      model: cfg.model, max_tokens: maxTokens, system, messages: msgs,
      tools: tools.map((t) => ({ name: t.name, description: t.description, input_schema: t.input_schema })),
    }, budget(cfg));
    const blocks: any[] = j.content ?? [];
    return {
      text: blocks.filter((b) => b.type === "text").map((b) => b.text).join("\n").trim(),
      toolCalls: blocks.filter((b) => b.type === "tool_use").map((b) => ({ id: b.id, name: b.name, args: b.input ?? {} })),
      usage: { input: j.usage?.input_tokens ?? 0, output: j.usage?.output_tokens ?? 0 },
    };
  }

  // Gemini 3 exige une thought_signature pour chaque appel d'outil lors du renvoi de l'historique.
  // Avec la rotation, l'appel d'outil peut venir d'un autre modèle que celui qui répond : on utilise donc toujours
  // la valeur documentée par Google qui désactive la vérification pour les appels précédents.
  const isGemini = GEMINI_BASE.test(cfg.base);
  const msgs: any[] = [{ role: "system", content: system }];
  for (const m of messages) {
    if (m.role === "user") msgs.push({ role: "user", content: m.content });
    else if (m.role === "assistant") {
      const o: any = { role: "assistant", content: m.content || null };
      if (m.tool_calls?.length) {
        o.tool_calls = m.tool_calls.map((tc) => {
          const extra = isGemini ? { google: { thought_signature: "skip_thought_signature_validator" } } : tc.extra;
          return {
            id: tc.id, type: "function",
            function: { name: tc.name, arguments: JSON.stringify(tc.args) },
            ...(extra ? { extra_content: extra } : {}),
          };
        });
      }
      msgs.push(o);
    } else msgs.push({ role: "tool", tool_call_id: m.tool_call_id, content: m.content });
  }
  const j = await openaiChat(cfg, {
    max_tokens: maxTokens, messages: msgs,
    ...(requireAction&&tools.length?{tool_choice:"required"}:{}),
    tools: tools.map((t) => ({ type: "function", function: { name: t.name, description: t.description, parameters: t.input_schema } })),
  });
  const msg = j.choices?.[0]?.message ?? {};
  return {
    text: cleanText(msg.content),
    toolCalls: (msg.tool_calls ?? msg.toolCalls ?? []).map((tc: any) => {
      let args: Json = {};
      const raw = tc.function?.arguments;
      if (raw && typeof raw === "object") args = raw;
      else { try { args = JSON.parse(raw || "{}"); } catch { /* arguments invalides : l'outil les refusera */ } }
      return { id: tc.id, name: tc.function?.name, args, ...(tc.extra_content ? { extra: tc.extra_content } : {}) };
    }),
    usage: { input: j.usage?.prompt_tokens ?? 0, output: j.usage?.completion_tokens ?? 0 },
  };
}

// Analyse d'image (vision) : lecture seule, aucune génération d'image.
export async function describeImage(cfg: LlmCfg, imageUrl: string, instruction: string): Promise<{ text: string; usage: { input: number; output: number } }> {
  if (cfg.provider === "anthropic") {
    const inlineJpeg = imageUrl.match(/^data:image\/jpeg;base64,([A-Za-z0-9+/=]+)$/);
    const source = inlineJpeg
      ? { type: "base64", media_type: "image/jpeg", data: inlineJpeg[1] }
      : { type: "url", url: imageUrl };
    const j = await post(`${cfg.base}/v1/messages`, { "x-api-key": cfg.key, "anthropic-version": "2023-06-01" }, {
      model: cfg.model, max_tokens: 1024,
      messages: [{ role: "user", content: [{ type: "image", source }, { type: "text", text: instruction }] }],
    }, budget(cfg));
    return {
      text: (j.content ?? []).filter((b: any) => b.type === "text").map((b: any) => b.text).join("\n"),
      usage: { input: j.usage?.input_tokens ?? 0, output: j.usage?.output_tokens ?? 0 },
    };
  }
  const j = await openaiChat(cfg, {
    max_tokens: 4096,
    messages: [{ role: "user", content: [{ type: "text", text: instruction }, { type: "image_url", image_url: { url: imageUrl } }] }],
  });
  return {
    text: cleanText(j.choices?.[0]?.message?.content),
    usage: { input: j.usage?.prompt_tokens ?? 0, output: j.usage?.completion_tokens ?? 0 },
  };
}

