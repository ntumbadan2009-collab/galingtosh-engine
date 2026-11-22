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
 if(/^(?:ok|okay|oui|oui je valide|d accord|daccord|c est bon|cest bon|parfait|vas y|go|je valide|je valide le plan|je confirme|je confirme le plan|je valide la production|lance|lance la production|lance le projet|tu peux commencer|commence la production|on y va|valide et lance|valider et produire)$/.test(value)) return "approve";
 if(/^(?:non|refuse|je refuse|annule|annule le plan|je ne valide pas|je refuse le plan|ne lance pas)$/.test(value)) return "reject";
 return null;
}
