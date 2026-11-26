/** A short reply has meaning only while an owned creative plan awaits approval.
 * Compound replies are never treated as acceptance.
 */
export function normalizePlanReply(raw: string): string {
 return raw.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLocaleLowerCase("fr")
  .replace(/[\p{Extended_Pictographic}\uFE0F\u200D]/gu,"")
  .replace(/[!,'’?.…\s-]+/g," ").trim();
}
export type PlanResponse="approve"|"reject"|null;
export function interpretPlanReply(raw:string):PlanResponse{
 const value=normalizePlanReply(raw);
 if(/^(?:ok|okay|oui|oui je valide|d accord|daccord|c est bon|cest bon|parfait|vas y|va y|vas y a toi de jouer|va y a toi de jouer|a toi de jouer|go|je valide|je valide le plan|je confirme|je confirme le plan|je valide la production|lance|lance la production|lance le projet|tu peux commencer|commence la production|on y va|valide et lance|valider et produire)$/.test(value)) return "approve";
 if(/^(?:non|refuse|je refuse|annule|annule le plan|je ne valide pas|je refuse le plan|ne lance pas)$/.test(value)) return "reject";
 return null;
}

export function directProduction(raw:string):number|null {
 const s=normalizePlanReply(raw);
 if(!/^(?:cree|creer|realise|produis|genere|fais|make|create|produce|je veux (?:creer|realiser|produire|faire|une|un))\b/.test(s))return null;
 if(!/\b(?:video|film|documentaire|clip|reportage|publicite|movie)\b/.test(s)||/\b(?:sans lancer|ne lance pas|propose seulement|avant de lancer|attends|valider avant|modifie|corrige)\b/.test(s))return null;
 const m=s.match(/\b(\d+)\s*(secondes?|secs?|s|minutes?|mins?|mn)\b(?:\s*(?:et\s*)?(\d+)\s*(?:secondes?|secs?|s)\b)?/);
 if(!m)return null;
 const n=Number(m[1])*(/^(?:min|mn)/.test(m[2])?60:1)+Number(m[3]??0);
 return Number.isInteger(n)&&n>=1&&n<=600?n:null;
}
