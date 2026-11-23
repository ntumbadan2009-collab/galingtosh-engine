/* Deterministic directing plan and evidence-first visual preflight.
 * Words from the approved narration stay the only source of code visuals.
 * Search tags and clip cut-detection never constitute visual proof.
 */
export const MIN_RELEVANCE = 0.82;
export const MIN_VISUAL_QUALITY = 0.55;
const MAX_CODE_SECONDS = 12;
const MAX_MEDIA_SECONDS = 16;

const clean = (x: unknown): string => typeof x === "string"
  ? x.normalize("NFKC").toLocaleLowerCase("fr").replace(/\s+/g, " ").trim() : "";
export function narrativeSource(scene: any): string {
  return String(scene?.narration?.text || scene?.narrativeGoal || "").trim();
}
export function quotedFromNarration(scene: any, quote: unknown): boolean {
  const source = clean(narrativeSource(scene));
  const q = clean(quote);
  return q.length >= 5 && q.length <= 280 && source.includes(q);
}
const validScore = (value: unknown, minimum: number): boolean =>
  typeof value === "number" && Number.isFinite(value) && value >= minimum && value <= 1;

export function verifiedVisualEvidence(scene: any, shot: any, media: any): boolean {
  const v = shot?.visualEvidence;
  if (!v || typeof v !== "object" || !media || !["image", "video"].includes(media.kind)) return false;
  if (v.verifiedBy !== "vision_observation_v1" || v.actualVisualAnalysis !== true ||
      v.mediaRef !== shot.mediaRef || !quotedFromNarration(scene, v.narrationQuote) ||
      !clean(v.visualIntent) || v.hasContradiction !== false) return false;
  if (media.source === "search" && v.licenseChecked !== true) return false;
  const needed = media.kind === "video" ? 3 : 1;
  if (!Array.isArray(v.samples) || v.samples.length < needed || v.samples.length > 4) return false;
  const times: number[] = [];
  for (const item of v.samples) {
    if (!item || !validScore(item.relevance, MIN_RELEVANCE) ||
        !validScore(item.visualQuality, MIN_VISUAL_QUALITY) ||
        !clean(item.description) || item.hasContradiction !== false) return false;
    if (media.kind === "video") {
      if (!Number.isFinite(item.atSec)) return false;
      times.push(Number(item.atSec));
    }
  }
  if (media.kind === "video") {
    const begin = Number(shot.sourceInSec ?? 0);
    const length = Number(shot.outSec) - Number(shot.inSec ?? 0);
    if (!Number.isFinite(begin) || !Number.isFinite(length) || length <= 0 ||
        !Number.isFinite(v.sourceInSec) || Math.abs(v.sourceInSec-begin) > 0.1 ||
        new Set(times.map(t => t.toFixed(2))).size < 3 ||
        times.some(t => t < begin-0.1 || t > begin+length+0.1)) return false;
  }
  return true;
}

export function narrativePreflight(film: any): string[] {
  const scenes = film?.scenes || [];
  const assets = new Map((film?.media || []).map((m: any) => [m.id, m]));
  const problems: string[] = [];
  if (!Array.isArray(scenes) || !scenes.length) return ["Le film ne contient pas de scènes."];
  for (let i = 0; i < scenes.length; i++) {
    const scene = scenes[i];
    if (!Array.isArray(scene?.shots) || !scene.shots.length) {
      problems.push(`Scène ${i+1} sans plan.`);
      continue;
    }
    if (!narrativeSource(scene)) {
      problems.push(`Scène ${i+1} sans narration ou intention narrative.`);
      continue;
    }
    for (let j = 0; j < scene.shots.length; j++) {
      const shot = scene.shots[j];
      const prefix = `Plan ${i+1}.${j+1}`;
      const duration = Number(shot.outSec)-Number(shot.inSec ?? 0);
      if (!Number.isFinite(duration) || duration <= 0) {
        problems.push(prefix+" : durée invalide."); continue;
      }
      if (shot.visualMode === "programmatic") {
        if (shot.mediaRef || !quotedFromNarration(scene, shot.visualText))
          problems.push(prefix+" : carte programmée sans citation fidèle du récit.");
        if (duration > MAX_CODE_SECONDS)
          problems.push(prefix+" : carte programmée trop longue (12 s maximum).");
        for (const issue of motionSpecIssues(scene,shot)) problems.push(prefix+" : "+issue);
      } else {
        if (!verifiedVisualEvidence(scene, shot, assets.get(shot.mediaRef)))
          problems.push(prefix+" : pertinence du média non vérifiée sur ses images réelles. Utilise verify_shot_media ou turn_shot_into_code.");
        if (duration > MAX_MEDIA_SECONDS)
          problems.push(prefix+" : plan vidéo ou photo trop long (16 s maximum).");
      }
    }
  }
  return problems;
}

export const MOTION_TYPES = ["focus", "steps", "timeline", "comparison"] as const;

const TEMPORAL = /(?:puis|ensuite|après|avant|d'abord|premièrement|secondement|troisièmement|initialement|finalement|au début|à la fin|then|before|after|first|next|finally)|\b(?:19|20)\d{2}\b/iu;
const CONTRAST = /(?:mais|cependant|pourtant|tandis que|alors que|contrairement|différent|différence|par contre|en revanche|but|while|unlike|versus)/iu;

/** Level-2 diagrams contain only ordered, literal excerpts already spoken. */
export function motionSpecIssues(scene: any, shot: any): string[] {
  const spec = shot?.visualSpec;
  if (spec == null) return [];
  if (typeof spec !== "object" || Array.isArray(spec) ||
      Object.keys(spec).sort().join(",") !== "items,type")
    return ["La spécification doit contenir uniquement type et items."];
  const kind = spec.type, items = spec.items;
  if (!MOTION_TYPES.includes(kind) || !Array.isArray(items))
    return ["Type de schéma ou éléments invalides."];
  const count = items.length;
  if (kind === "focus" && count !== 1 ||
      kind === "comparison" && count !== 2 ||
      ["steps", "timeline"].includes(kind) && (count < 2 || count > 4))
    return ["Nombre d'éléments non pris en charge pour ce schéma."];
  const quote = clean(shot?.visualText), narrative = clean(narrativeSource(scene));
  if (!quote || !narrative.includes(quote))
    return ["Le schéma ne reprend pas la narration de la scène."];
  if (kind === "timeline" && !TEMPORAL.test(quote))
    return ["Une chronologie exige une suite temporelle explicite."];
  if (kind === "comparison" && !CONTRAST.test(quote))
    return ["Une comparaison exige un contraste explicite dans le récit."];
  let cursor=0;
  for (let i=0;i<count;i++) {
    const item=items[i];
    if (!item || typeof item !== "object" || Array.isArray(item) ||
        Object.keys(item).join(",")!=="text") return [`Bloc ${i+1} invalide.`];
    const text=clean(item.text);
    if (text.length < 5 || text.length > 125) return [`Bloc ${i+1} : citation trop courte ou trop longue.`];
    const position=quote.indexOf(text,cursor);
    if (position<0) return [`Bloc ${i+1} : élément absent ou hors ordre de la narration.`];
    cursor=position+text.length;
  }
  return [];
}

export interface NarrativeBeat {
  startSec: number;
  endSec: number;
  quote: string;
  presentation: "question"|"focus"|"contrast";
}
/** Split into dense intelligible phrases: no invented narration or fake data. */
export function planNarrativeBeats(text: string, durationSeconds: number): NarrativeBeat[] {
  if (typeof text !== "string" || !text.trim() || !Number.isFinite(durationSeconds) || durationSeconds <= 0)
    throw new Error("Texte narratif et durée valides requis.");
  const tokens = [...text.matchAll(/\S+/gu)].map(m => ({word: m[0], from: m.index!, to: m.index!+m[0].length}));
  if (!tokens.length) throw new Error("Narration vide.");
  const desiredCount = Math.max(1, Math.ceil(durationSeconds/6));
  const maxWords = Math.min(18, Math.max(5, Math.ceil(tokens.length/desiredCount)));
  const quotes: {from: number; to: number; words: number}[] = [];
  for (let start=0; start<tokens.length;) {
    let end = Math.min(tokens.length, start+maxWords);
    // Prefer a natural punctuation boundary near the intended cut.
    const earliest = Math.max(start+4, end-4);
    for (let idx=end-1; idx>=earliest; idx--) {
      if (/[.!?;:,]$/.test(tokens[idx].word)) { end=idx+1; break; }
    }
    quotes.push({from:tokens[start].from, to:tokens[end-1].to, words:end-start});
    start=end;
  }
  const sumWords = quotes.reduce((a,b)=>a+b.words,0);
  let cursor=0;
  return quotes.map((item,i)=>{
    const ending = i===quotes.length-1?durationSeconds:durationSeconds*quotes.slice(0,i+1).reduce((a,b)=>a+b.words,0)/sumWords;
    const quote=text.slice(item.from,item.to).trim();
    const style: NarrativeBeat["presentation"] = quote.includes("?") ? "question"
      : /\b(mais|cependant|pourtant|contrairement|however|but)\b/i.test(quote) ? "contrast" : "focus";
    const beat={startSec:Number(cursor.toFixed(3)),endSec:Number(ending.toFixed(3)),quote,presentation:style};
    cursor=ending;return beat;
  });
}
