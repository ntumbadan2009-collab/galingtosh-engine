// Editorial contract: genre-sensitive direction, not a clone of a creator.
export const EDITORIAL_DIRECTION = "NIVEAU 3 — RÉALISATION YOUTUBE : commence par une promesse narrative concrète et honnête, sans générique vide. Construis une progression (question, contexte, démonstration, révélation, résolution) adaptée au genre et à la durée. Pour chaque scène, choisis un objectif émotionnel et un langage visuel qui explique les idées, pas seulement des cartes de texte. Inspire-toi des principes du documentaire, de la vulgarisation et des essais vidéo : preuve réelle, contraste, chronologie, démonstration, respiration. Change de plan quand l'information évolue; maintiens un plan plus longtemps si la compréhension le nécessite. Pas de changement arbitraire ni de montage frénétique. Vérifie les citations, sources, licences et la concordance de chaque plan. Pas de médias générés par IA, ni de chiffres inventés. Prépare la voix et la musique procédurale par scène, avec silences intentionnels et effets utiles seulement; ne prétends pas disposer d'une banque sonore ou de formes graphiques non prises en charge. Utilise des sous-titres si demandés; évite de recouvrir les éléments utiles. Couvre tout le minutage sans chevauchement, ni plan éclair. Avant rendu, relis le film et corrige les défauts identifiés. Le contrôle technique final n'est pas une preuve de qualité artistique.";
export function editorialTimelineIssues(film: any): string[] {
  if (film?.info?.editorialLevel !== 3) return [];
  const issues: string[] = [];
  for (const [i, scene] of (film.scenes ?? []).entries()) {
    const duration = Number(scene.durationSec);
    let cursor = 0;
    const shots = [...(scene.shots ?? [])].sort((a,b)=>(a.order??0)-(b.order??0));
    for (const [j, shot] of shots.entries()) {
      const start = Number(shot.inSec), end = Number(shot.outSec);
      if (![start,end,duration].every(Number.isFinite) || Math.abs(start-cursor)>0.08 || end>duration+0.08)
        issues.push("Scène "+(i+1)+", plan "+(j+1)+" : trou, chevauchement ou dépassement.");
      if (end-start < Math.min(1,duration)-0.001) issues.push("Plan trop bref pour être lisible.");
      cursor=end;
    }
    if (Math.abs(cursor-duration)>0.08) issues.push("Scène "+(i+1)+" : minutage incomplet.");
  }
  return issues;
}
