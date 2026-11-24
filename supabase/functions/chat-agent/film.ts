// Structure FILM JSON + opérations contrôlées (fonctions pures).
// L'agent ne modifie jamais le JSON autrement que par applyOperation().

import { quotedFromNarration, verifiedVisualEvidence, motionSpecIssues, MOTION_TYPES } from "./narrative.ts";
export type Json = Record<string, any>;

export const ASPECTS: Record<string, [number, number]> = {
  "16:9": [1920, 1080], "9:16": [1080, 1920], "1:1": [1080, 1080],
  "4:3": [1440, 1080], "4:5": [1080, 1350], "21:9": [2560, 1080],
};
export const FILM_TYPES = [
  "documentary", "fiction", "short_film", "music_video", "ad", "institutional",
  "reportage", "educational", "social", "photo_story", "custom",
];
export const AUDIO_KINDS = ["voiceover", "music", "sfx", "dialogue"];
export const MEDIA_KINDS = ["image", "video", "audio", "svg", "chart", "animation", "model3d"];
const RESOLUTIONS = ["720p", "1080p"];

// Listes « standard » : un type hors liste est accepté (le montage ne doit pas être limité)
// mais un avertissement signale que le worker devra le prendre en charge.
const STD_CAMERA = ["ken_burns", "dolly", "pan", "tilt", "zoom_in", "zoom_out", "none"];
const STD_TRANSITIONS = ["cut", "dissolve", "fade", "slide", "zoom", "wipe"];

const nid = (p: string) => `${p}_${crypto.randomUUID().slice(0, 8)}`;
function fail(msg: string): never { throw new Error(msg); }
function req(a: Json, k: string) {
  if (a[k] === undefined || a[k] === null || a[k] === "") fail(`Paramètre manquant : ${k}`);
  return a[k];
}
function numIn(v: any, k: string, min: number, max: number): number {
  const n = Number(v);
  if (v === null || v === "" || !Number.isFinite(n) || n < min || n > max) fail(`${k} doit être un nombre entre ${min} et ${max}`);
  return n;
}
function oneOf(v: any, k: string, list: string[]): string {
  if (!list.includes(v)) fail(`${k} invalide ("${v}"). Valeurs : ${list.join(", ")}`);
  return v;
}
function str(v: any, k: string, max = 2000): string {
  if (typeof v !== "string" || !v.trim()) fail(`${k} doit être un texte non vide`);
  if (v.length > max) fail(`${k} trop long (max ${max} caractères)`);
  return v.trim();
}

export function defaultFilm(title: string, type = "custom", language = "fr"): Json {
  const [width, height] = ASPECTS["16:9"];
  return {
    info: { title, type, language, visualPolicy: "strict", editorialLevel: 5 },
    format: { aspect: "16:9", width, height, fps: 30 },
    scenes: [], characters: [], media: [], audio: { tracks: [] },
    effects: [], transitions: [], subtitles: [],
    render: { resolution: "1080p", audioBitrateKbps: 192, videoBitrateMbps: 8 },
  };
}

const findScene = (f: Json, id: string): Json =>
  f.scenes.find((s: Json) => s.id === id) ?? fail(`Scène introuvable : ${id}`);

function findShot(f: Json, id: string): { scene: Json; shot: Json } {
  for (const scene of f.scenes) {
    const shot = scene.shots.find((x: Json) => x.id === id);
    if (shot) return { scene, shot };
  }
  return fail(`Plan introuvable : ${id}`);
}

const renum = (arr: Json[]) => arr.forEach((x, i) => { x.order = i + 1; });

function insertAt(arr: Json[], item: Json, pos?: number) {
  if (pos === undefined || pos === null) { arr.push(item); return; }
  const idx = Math.trunc(numIn(pos, "position", 1, arr.length + 1)) - 1;
  arr.splice(idx, 0, item);
}

function mediaIn(f: Json, id: string) {
  if (!f.media.some((m: Json) => m.id === id)) {
    fail(`Média absent du film : ${id}. Ajoute-le d'abord (attach_media ou add_found_media).`);
  }
}

function charIds(f: Json, ids: any): string[] {
  if (!Array.isArray(ids)) fail("characters doit être une liste d'identifiants");
  for (const id of ids) if (!f.characters.some((c: Json) => c.id === id)) fail(`Personnage introuvable : ${id}`);
  return ids;
}

function camera(c: any, warnings: string[]): Json {
  if (c === undefined || c === null) return { type: "none" };
  const cam = typeof c === "string" ? { type: c } : { ...c };
  const type = str(cam.type, "camera.type", 60);
  if (!STD_CAMERA.includes(type)) warnings.push(`Mouvement de caméra non standard "${type}" : le worker de rendu devra le prendre en charge.`);
  return cam.params ? { type, params: cam.params } : { type };
}

function upsertMedia(f: Json, m: Json) {
  const id = str(m?.id, "media.id", 100);
  oneOf(m.kind, "media.kind", MEDIA_KINDS);
  if (m.source === "search") {
    const p = m.provenance;
    if (!p?.license || !p?.url || !p?.author || !p?.source) fail("Un média issu d'une recherche exige une provenance complète (auteur, source, licence, url)");
  }
  const i = f.media.findIndex((x: Json) => x.id === id);
  if (i >= 0) f.media[i] = { ...f.media[i], ...m }; else f.media.push(m);
}

function validateCues(cues: any): Json[] {
  if (!Array.isArray(cues) || cues.length > 2000) fail("cues doit être une liste (max 2000)");
  return cues.map((c: Json, i: number) => {
    const startSec = numIn(c.startSec, `cues[${i}].startSec`, 0, 36000);
    const endSec = numIn(c.endSec, `cues[${i}].endSec`, 0, 36000);
    if (endSec <= startSec) fail(`cues[${i}] : endSec doit être supérieur à startSec`);
    return { startSec, endSec, text: str(c.text, `cues[${i}].text`, 500) };
  }).sort((x, y) => x.startSec - y.startSec);
}

export function applyOperation(src: Json, name: string, a: Json): { film: Json; result: Json } {
  const f: Json = structuredClone(src);
  f.info ??= {}; f.format ??= {}; f.render ??= {};
  f.scenes ??= []; f.characters ??= []; f.media ??= [];
  f.audio ??= {}; f.audio.tracks ??= [];
  f.effects ??= []; f.transitions ??= []; f.subtitles ??= [];
  for (const s of f.scenes) s.shots ??= [];
  const warnings: string[] = [];
  let result: Json = {};

  switch (name) {
    case "set_project_info": {
      if (a.title !== undefined) f.info.title = str(a.title, "title", 200);
      if (a.type !== undefined) f.info.type = oneOf(a.type, "type", FILM_TYPES);
      if (a.language !== undefined) f.info.language = str(a.language, "language", 10);
      if (a.synopsis !== undefined) f.info.synopsis = str(a.synopsis, "synopsis", 4000);
      break;
    }
    case "set_format": {
      const aspect = oneOf(a.aspect, "aspect", [...Object.keys(ASPECTS), "custom"]);
      let w: number, h: number;
      if (aspect === "custom") {
        w = numIn(req(a, "width"), "width", 16, 7680);
        h = numIn(req(a, "height"), "height", 16, 7680);
        if (!Number.isInteger(w) || !Number.isInteger(h) || w % 2 || h % 2) fail("width et height doivent être des entiers pairs (encodage H.264)");
      } else {
        [w, h] = ASPECTS[aspect];
      }
      f.format = { aspect, width: w, height: h, fps: a.fps !== undefined ? numIn(a.fps, "fps", 1, 30) : (f.format.fps ?? 30) };
      break;
    }
    case "set_render_params": {
      const r = f.render;
      if (a.targetDurationSec !== undefined) r.targetDurationSec = numIn(a.targetDurationSec, "targetDurationSec", 1, 600);
      if (a.resolution !== undefined) r.resolution = oneOf(a.resolution, "resolution", RESOLUTIONS);
      if (a.audioBitrateKbps !== undefined) r.audioBitrateKbps = numIn(a.audioBitrateKbps, "audioBitrateKbps", 32, 512);
      if (a.videoBitrateMbps !== undefined) r.videoBitrateMbps = numIn(a.videoBitrateMbps, "videoBitrateMbps", 1, 80);
      break;
    }
    case "add_character": {
      const c: Json = { id: nid("ch"), name: str(a.name, "name", 100) };
      if (a.description) c.description = str(a.description, "description", 1000);
      if (a.voiceRef) c.voiceRef = str(a.voiceRef, "voiceRef", 100);
      f.characters.push(c);
      result = { character_id: c.id };
      break;
    }
    case "update_character": {
      const c = f.characters.find((x: Json) => x.id === a.character_id) ?? fail(`Personnage introuvable : ${a.character_id}`);
      if (a.name !== undefined) c.name = str(a.name, "name", 100);
      if (a.description !== undefined) c.description = str(a.description, "description", 1000);
      if (a.voiceRef !== undefined) c.voiceRef = str(a.voiceRef, "voiceRef", 100);
      break;
    }
    case "add_scene": {
      const sc: Json = {
        id: nid("sc"), order: 0, title: str(a.title, "title", 200),
        narrativeGoal: str(a.narrativeGoal, "narrativeGoal", 1000),
        durationSec: numIn(req(a, "durationSec"), "durationSec", 0.5, 3600), shots: [],
      };
      if (a.mood) sc.mood = str(a.mood, "mood", 60);
      if (a.characters) sc.characters = charIds(f, a.characters);
      insertAt(f.scenes, sc, a.position);
      renum(f.scenes);
      result = { scene_id: sc.id, order: sc.order };
      break;
    }
    case "update_scene": {
      const s = findScene(f, req(a, "scene_id"));
      if (a.title !== undefined) s.title = str(a.title, "title", 200);
      if (a.narrativeGoal !== undefined) s.narrativeGoal = str(a.narrativeGoal, "narrativeGoal", 1000);
      if (a.durationSec !== undefined) {
        s.durationSec = numIn(a.durationSec, "durationSec", 0.5, 3600);
        if (s.narration) s.narration.targetDurationSec = s.durationSec;
      }
      if (a.mood !== undefined) s.mood = a.mood === null ? undefined : str(a.mood, "mood", 60);
      if (a.characters !== undefined) s.characters = charIds(f, a.characters);
      for (const sh of s.shots) if (sh.outSec > s.durationSec) warnings.push(`Le plan ${sh.id} dépasse la durée de la scène (${sh.outSec}s > ${s.durationSec}s).`);
      break;
    }
    case "set_scene_narration": {
      const scene = findScene(f, req(a, "scene_id"));
      const text = str(a.text, "text", 4000).trim();
      if (!text) fail("La narration de la scène ne peut pas être vide.");
      const targetDurationSec = numIn(a.targetDurationSec ?? scene.durationSec, "targetDurationSec", 0.5, 3600);
      const oldDuration = Number(scene.durationSec) || targetDurationSec;
      if (Math.abs(targetDurationSec - oldDuration) > 0.001) {
        const ratio = targetDurationSec / oldDuration;
        for (const shot of scene.shots ?? []) {
          shot.inSec = Math.max(0, Number(shot.inSec ?? 0) * ratio);
          shot.outSec = Math.max(shot.inSec + 0.05, Number(shot.outSec ?? oldDuration) * ratio);
        }
        scene.durationSec = targetDurationSec;
      }
      const ratePercent=numIn(a.ratePercent??scene.narration?.ratePercent??0,"ratePercent",-20,20);
      const pitchHz=numIn(a.pitchHz??scene.narration?.pitchHz??0,"pitchHz",-12,12);
      if(!Number.isInteger(ratePercent)||!Number.isInteger(pitchHz))fail("Direction vocale : valeurs entières requises.");
      scene.narration = {
        text,ratePercent,pitchHz,
        targetDurationSec,
        language: str(a.language ?? f.info.language ?? "fr", "language", 10),
        voice: str(a.voice ?? "default", "voice", 80),
      };
      result = { scene_id: scene.id, targetDurationSec };
      break;
    }
    case "align_narration_durations": {
      if (!Array.isArray(a.segments)) fail("segments doit être une liste.");
      const oldSpans: Array<[number, number]> = [];
      let oldOffset = 0;
      for (const scene of f.scenes) {
        const duration = Math.max(0, Number(scene.durationSec) || 0);
        oldSpans.push([oldOffset, oldOffset + duration]);
        oldOffset += duration;
      }
      let aligned = 0;
      for (const item of a.segments) {
        const scene = findScene(f, req(item, "sceneId"));
        if (!scene.narration) fail(`Aucune narration enregistrée pour la scène ${item.sceneId}.`);
        const measured = numIn(item.durationSec, "durationSec", 0.5, 3600);
        const previous = Number(scene.durationSec) || measured;
        const ratio = measured / previous;
        for (const shot of scene.shots ?? []) {
          shot.inSec = Math.max(0, Number(shot.inSec ?? 0) * ratio);
          shot.outSec = Math.max(shot.inSec + 0.05, Number(shot.outSec ?? previous) * ratio);
        }
        scene.durationSec = measured;
        scene.narration.measuredDurationSec = measured;
        if (item.ttsProvider === "edge-tts" || item.ttsProvider === "piper") scene.narration.ttsProvider = item.ttsProvider;
        aligned++;
      }
      let newOffset = 0;
      const newSpans = f.scenes.map((scene: Json) => {
        const duration = Math.max(0, Number(scene.durationSec) || 0);
        const span: [number, number] = [newOffset, newOffset + duration];
        newOffset += duration;
        return span;
      });
      const remapTime = (time: number) => {
        for (let i = 0; i < oldSpans.length; i++) {
          const [start, end] = oldSpans[i];
          if (start <= time && time <= end && end > start) {
            const [nextStart, nextEnd] = newSpans[i];
            return nextStart + (time - start) * (nextEnd - nextStart) / (end - start);
          }
        }
        return time > oldOffset ? time + newOffset - oldOffset : time;
      };
      for (const track of f.subtitles) for (const cue of track.cues ?? []) {
        if (Number.isFinite(Number(cue.startSec))) cue.startSec = Math.max(0, remapTime(Number(cue.startSec)));
        if (Number.isFinite(Number(cue.endSec))) cue.endSec = Math.max(0, remapTime(Number(cue.endSec)));
      }
      if ([3,4,5].includes(f.info?.editorialLevel)) for (const track of f.audio?.tracks ?? []) for (const event of track.events ?? []) {
        const start = Number(event.startSec), end = start + Number(event.durationSec);
        if (Number.isFinite(start) && Number.isFinite(end)) {
          event.startSec = Math.max(0, remapTime(start));
          event.durationSec = Math.max(0.001, remapTime(end)-remapTime(start));
        }
      }
      result = { aligned_scenes: aligned };
      break;
    }
    case "remove_scene": {
      const s = findScene(f, req(a, "scene_id"));
      const shotIds = new Set(s.shots.map((x: Json) => x.id));
      f.scenes = f.scenes.filter((x: Json) => x.id !== s.id);
      f.transitions = f.transitions.filter((t: Json) => !shotIds.has(t.atShotId));
      renum(f.scenes);
      result = { removed_shots: shotIds.size };
      break;
    }
    case "reorder_scenes": {
      const ids = a.scene_ids;
      if (!Array.isArray(ids) || ids.length !== f.scenes.length || new Set(ids).size !== ids.length) fail("scene_ids doit contenir chaque scène exactement une fois");
      f.scenes = ids.map((id: string) => findScene(f, id));
      renum(f.scenes);
      break;
    }
    case "set_motion_visual": {
      const {scene,shot}=findShot(f,req(a,"shot_id"));
      if(shot.visualMode!=="programmatic"||shot.mediaRef)
        fail("Une animation graphique ne peut être ajoutée qu'à un plan généré par code.");
      const kind=oneOf(a.visualType,"visualType",[...MOTION_TYPES]);
      if(!Array.isArray(a.visualItems))fail("visualItems doit être un tableau de citations exactes.");
      const spec={type:kind,items:a.visualItems.map((text:unknown)=>({text}))};
      const issues=motionSpecIssues(scene,{...shot,visualSpec:spec});
      if(issues.length)fail(issues.join(" "));
      shot.visualSpec=spec;
      result={shot_id:shot.id,visualType:kind,items:spec.items.length};
      break;
    }
    case "add_code_shot": {
      const scene = findScene(f, req(a, "scene_id"));
      const quote = str(a.visualText, "visualText", 280);
      if (!quotedFromNarration(scene, quote)) fail("L'illustration par code doit citer exactement un passage du récit de cette scène.");
      const inSec = numIn(a.inSec ?? 0, "inSec", 0, 3600);
      const outSec = numIn(req(a, "outSec"), "outSec", 0.1, 3600);
      if (outSec <= inSec || outSec-inSec > 12.0) fail("Un plan programmatique doit durer au maximum 12 secondes.");
      const cardStyle = a.cardStyle === undefined ? "focus" : oneOf(a.cardStyle, "cardStyle", ["focus","question","contrast","process"]);
      const sh: Json = {
        id: nid("sh"), order: 0, inSec, outSec,
        camera: {type:"ken_burns"}, visualMode:"programmatic",
        visualText:quote, cardStyle,
      };
      if(a.visualType!==undefined){
        const kind=oneOf(a.visualType,"visualType",[...MOTION_TYPES]);
        if(!Array.isArray(a.visualItems))fail("visualItems manquant pour l'animation.");
        const spec={type:kind,items:a.visualItems.map((text:unknown)=>({text}))};
        const issues=motionSpecIssues(scene,{...sh,visualSpec:spec});
        if(issues.length)fail(issues.join(" "));
        sh.visualSpec=spec;
      }
      insertAt(scene.shots, sh, a.position);
      renum(scene.shots);
      result = {shot_id:sh.id, scene_id:scene.id, created_programmatically:true, visualType:sh.visualSpec?.type??"legacy", visualText:quote};
      break;
    }
    case "turn_shot_into_code": {
      const { scene, shot } = findShot(f, req(a, "shot_id"));
      const quote = str(a.visualText, "visualText", 280);
      if (!quotedFromNarration(scene, quote)) fail("Le texte de la carte doit provenir exactement de la narration.");
      if (Number(shot.outSec)-Number(shot.inSec) > 12.0)
        fail("Découpe ce plan en morceaux de 12 secondes maximum avant de convertir en illustration par code.");
      shot.visualMode = "programmatic";
      shot.visualText = quote;
      shot.cardStyle = a.cardStyle === undefined ? "focus" : oneOf(a.cardStyle, "cardStyle", ["focus","question","contrast","process"]);
      shot.camera = {type:"ken_burns"};
      delete shot.mediaRef; delete shot.visualEvidence; delete shot.sourceInSec; delete shot.visualSpec;
      if(a.visualType!==undefined){
        const kind=oneOf(a.visualType,"visualType",[...MOTION_TYPES]);
        if(!Array.isArray(a.visualItems))fail("visualItems manquant pour l'animation.");
        const spec={type:kind,items:a.visualItems.map((text:unknown)=>({text}))};
        const issues=motionSpecIssues(scene,{...shot,visualSpec:spec});
        if(issues.length)fail(issues.join(" "));
        shot.visualSpec=spec;
      }
      result = {shot_id:shot.id, scene_id:scene.id, converted_to_code:true,visualType:shot.visualSpec?.type??"legacy"};
      break;
    }
    case "record_visual_verification": {
      const { scene, shot } = findShot(f, req(a, "shot_id"));
      const media = f.media.find((m:Json)=>m.id===shot.mediaRef);
      // Only the internal vision tool can call this operation; the schema
      // still validates every sample, source timestamp, quote and media ref.
      const candidate = {...shot, visualEvidence:a.evidence};
      if (!verifiedVisualEvidence(scene,candidate,media??null))
        fail("Preuve de pertinence visuelle invalide.");
      shot.visualEvidence = a.evidence;
      shot.visualMode = "media";
      delete shot.visualText; delete shot.cardStyle;
      result = {shot_id:shot.id, visual_verified:true};
      break;
    }
    case "add_shot": {
      const s = findScene(f, req(a, "scene_id"));
      const inSec = numIn(a.inSec ?? 0, "inSec", 0, 3600);
      const outSec = numIn(req(a, "outSec"), "outSec", 0.1, 3600);
      if (outSec <= inSec) fail("outSec doit être supérieur à inSec");
      const sh: Json = { id: nid("sh"), order: 0, camera: camera(a.camera, warnings), inSec, outSec };
      if (a.sourceInSec !== undefined) sh.sourceInSec = numIn(a.sourceInSec, "sourceInSec", 0, 36000);
      if (a.mediaRef) { mediaIn(f, a.mediaRef); sh.mediaRef = a.mediaRef; }
      if (outSec > s.durationSec) warnings.push(`Le plan dépasse la durée de la scène (${outSec}s > ${s.durationSec}s).`);
      insertAt(s.shots, sh, a.position);
      renum(s.shots);
      result = { shot_id: sh.id, scene_id: s.id, order: sh.order };
      break;
    }
    case "update_shot": {
      const { scene, shot } = findShot(f, req(a, "shot_id"));
      if (a.camera !== undefined) shot.camera = camera(a.camera, warnings);
      if (a.mediaRef !== undefined || a.inSec !== undefined ||
          a.outSec !== undefined || a.sourceInSec !== undefined) delete shot.visualEvidence;
      if (a.inSec !== undefined) shot.inSec = numIn(a.inSec, "inSec", 0, 3600);
      if (a.outSec !== undefined) shot.outSec = numIn(a.outSec, "outSec", 0.1, 3600);
      if (a.sourceInSec !== undefined) shot.sourceInSec = numIn(a.sourceInSec, "sourceInSec", 0, 36000);
      if (shot.outSec <= shot.inSec) fail("outSec doit être supérieur à inSec");
      if (a.mediaRef !== undefined) {
        if (a.mediaRef === null) delete shot.mediaRef; else { mediaIn(f, a.mediaRef); shot.mediaRef = a.mediaRef; }
        if (a.mediaRef) {shot.visualMode="media";delete shot.visualText;delete shot.cardStyle;delete shot.visualSpec;}
      }
      if (shot.outSec > scene.durationSec) warnings.push(`Le plan dépasse la durée de la scène (${shot.outSec}s > ${scene.durationSec}s).`);
      break;
    }
    case "remove_shot": {
      const { scene, shot } = findShot(f, req(a, "shot_id"));
      scene.shots = scene.shots.filter((x: Json) => x.id !== shot.id);
      f.transitions = f.transitions.filter((t: Json) => t.atShotId !== shot.id);
      renum(scene.shots);
      break;
    }
    case "register_media": {
      upsertMedia(f, a.media);
      result = { media_id: a.media.id };
      break;
    }
    case "attach_media": {
      const { shot } = findShot(f, req(a, "shot_id"));
      upsertMedia(f, a.media);
      shot.mediaRef = a.media.id;
      shot.visualMode="media";
      delete shot.visualEvidence; delete shot.visualText; delete shot.cardStyle; delete shot.visualSpec;
      result = { shot_id: shot.id, media_id: a.media.id };
      break;
    }
    case "update_media_analysis": {
      const m = f.media.find((x: Json) => x.id === a.media_id);
      if (!m) { warnings.push(`Média ${a.media_id} absent du film : analyse enregistrée en base uniquement.`); break; }
      m.analysis = { ...(m.analysis ?? {}), ...(a.analysis ?? {}) };
      break;
    }
    case "add_audio_track": {
      const kind = oneOf(a.kind, "kind", AUDIO_KINDS);
      if (kind !== "sfx" && !a.mediaRef && !a.tts) fail("Une piste audio exige mediaRef (fichier) ou tts (voix off synthétisée)");
      const t: Json = { id: nid("au"), kind, events: [] };
      if (a.mediaRef) { mediaIn(f, a.mediaRef); t.mediaRef = a.mediaRef; }
      if (kind === "sfx") {
        t.expectedContent = str(a.expectedContent, "expectedContent", 300);
        if (!Array.isArray(a.events) || a.events.length === 0) fail("Une piste sfx exige au moins un événement avec son emplacement et sa durée.");
      }
      if (a.tts) {
        t.tts = {
          provider: a.tts.provider ?? "edge-tts", voice: a.tts.voice ?? "default",
          text: str(a.tts.text, "tts.text", 4000), language: a.tts.language ?? f.info.language ?? "fr",
        };
      }
      if (a.volumeDb !== undefined) t.volumeDb = numIn(a.volumeDb, "volumeDb", -60, 12);
      for (const [i, e] of (a.events ?? []).entries()) {
        t.events.push({ id: nid("ev"), startSec: numIn(e.startSec, `events[${i}].startSec`, 0, 36000), durationSec: numIn(e.durationSec, `events[${i}].durationSec`, 0.05, 36000) });
      }
      f.audio.tracks.push(t);
      result = { track_id: t.id };
      break;
    }
    case "attach_verified_sound": {
      const {scene,shot}=findShot(f,req(a,"shot_id"));
      const e=a.evidence;
      if(!e||e.verifiedBy!=="gemini_audio_observation_v1"||e.actualAudioAnalysis!==true||e.match!=="pass"||
          e.containsSpeech!==false||e.containsMusic!==false||!(/^[0-9a-f]{64}$/).test(e.sourceSha256??"")||
          e.shotId!==shot.id||e.mediaRef!==a.media?.id||a.media?.kind!=="audio"||a.media?.source!=="search")
        fail("Preuve sonore invalide.");
      if(!quotedFromNarration(scene,e.narrationQuote))fail("Citation du son absente de la narration.");
      const visualQuote=shot.visualMode==="programmatic"?shot.visualText:shot.visualEvidence?.narrationQuote;
      if(typeof visualQuote!=="string"||!quotedFromNarration({narration:{text:visualQuote}},e.narrationQuote))fail("Le son doit concerner le plan choisi.");
      const duration=numIn(e.durationSec,"durationSec",.25,12),offset=numIn(e.offsetSec,"offsetSec",0,16);
      numIn(e.sourceInSec,"sourceInSec",0,3600);
      if(offset+duration>Number(shot.outSec)-Number(shot.inSec)+.001)fail("Le son dépasse le plan.");
      upsertMedia(f,a.media);
      let base=0;
      for(const sc of [...f.scenes].sort((x,y)=>(x.order??0)-(y.order??0))){if(sc.id===scene.id)break;base+=Number(sc.durationSec);}
      const t={id:nid("au"),kind:"sfx",mediaRef:a.media.id,expectedContent:str(e.expectedContent,"expectedContent",300),soundEvidence:e,volumeDb:-10,
        events:[{id:nid("ev"),startSec:base+Number(shot.inSec)+offset,durationSec:duration}]};
      f.audio.tracks.push(t);
      result={track_id:t.id,verified:true};
      break;
    }
    case "remove_audio_track": {
      const n = f.audio.tracks.length;
      f.audio.tracks = f.audio.tracks.filter((t: Json) => t.id !== a.track_id);
      if (f.audio.tracks.length === n) fail(`Piste audio introuvable : ${a.track_id}`);
      break;
    }
    case "update_audio_track": {
      const t = f.audio.tracks.find((x: Json) => x.id === req(a, "track_id"));
      if (!t) fail(`Piste audio introuvable : ${a.track_id}`);
      if (a.volumeDb !== undefined) t.volumeDb = numIn(a.volumeDb, "volumeDb", -60, 12);
      if (a.events !== undefined) {
        if(t.soundEvidence)fail("Pour déplacer un son vérifié, supprime la piste et vérifie à nouveau le plan.");
        if (!Array.isArray(a.events) || a.events.length > 100) fail("events invalide (max 100)");
        t.events = a.events.map((e: Json, i: number) => ({ id: e.id ?? nid("ev"),
          startSec: numIn(e.startSec, `events[${i}].startSec`, 0, 36000),
          durationSec: numIn(e.durationSec, `events[${i}].durationSec`, 0.05, 36000) }));
      }
      break;
    }
    case "set_editorial_accents": {
      if (typeof a.enabled !== "boolean") fail("enabled doit être booléen");
      f.audio.editorialAccents = a.enabled;
      result = { enabled: a.enabled };
      break;
    }
    case "set_procedural_music": {
      const music = f.audio.proceduralMusic ?? { enabled: false, volumeDb: -15, cues: [] };
      if (a.enabled !== undefined) {
        if (typeof a.enabled !== "boolean") fail("enabled doit être booléen");
        music.enabled = a.enabled;
      }
      if (a.volumeDb !== undefined) music.volumeDb = numIn(a.volumeDb, "volumeDb", -60, 0);
      f.audio.proceduralMusic = music;
      break;
    }
    case "set_scene_music": {
      findScene(f, req(a, "scene_id"));
      const mood = oneOf(a.mood, "mood", ["silence", "calm", "hopeful", "tense", "sad", "wonder", "neutral"]);
      const intensity = mood === "silence" ? 0 : numIn(a.intensity ?? 0.45, "intensity", 0, 1);
      const music = f.audio.proceduralMusic ?? { enabled: true, volumeDb: -15, cues: [] };
      music.enabled = true;
      music.cues = (music.cues ?? []).filter((c: Json) => c.sceneId !== a.scene_id);
      music.cues.push({ sceneId: a.scene_id, mood, intensity });
      f.audio.proceduralMusic = music;
      break;
    }
    case "update_subtitles": {
      const cues = validateCues(a.cues);
      let t = a.track_id ? f.subtitles.find((x: Json) => x.id === a.track_id) : f.subtitles.find((x: Json) => x.language === a.language);
      if (a.track_id && !t) fail(`Piste de sous-titres introuvable : ${a.track_id}`);
      if (!t) {
        t = { id: nid("st"), language: str(a.language, "language", 10), cues: [] };
        f.subtitles.push(t);
      }
      t.cues = cues;
      result = { track_id: t.id, cues: cues.length };
      break;
    }
    case "set_transition": {
      const { shot } = findShot(f, req(a, "at_shot_id"));
      const type = str(a.type, "type", 60);
      if (!STD_TRANSITIONS.includes(type)) warnings.push(`Transition non standard "${type}" : le worker de rendu devra la prendre en charge.`);
      const durationSec = numIn(a.durationSec ?? 0.5, "durationSec", 0, 10);
      const i = f.transitions.findIndex((t: Json) => t.atShotId === shot.id);
      const tr = { id: i >= 0 ? f.transitions[i].id : nid("tr"), type, atShotId: shot.id, durationSec };
      if (i >= 0) f.transitions[i] = tr; else f.transitions.push(tr);
      result = { transition_id: tr.id };
      break;
    }
    case "add_effect": {
      const e: Json = { id: nid("fx"), type: str(a.type, "type", 60), target: str(a.target, "target", 100), params: a.params ?? {} };
      e.type = e.type === "title_overlay" ? "text_overlay" : e.type;
      oneOf(e.type, "effect.type", ["fade_in","fade_out","grayscale","vignette","text_overlay"]);
      if (e.target !== "film" && !f.scenes.some((sc:Json)=>sc.id===e.target || sc.shots.some((sh:Json)=>sh.id===e.target))) fail("Cible d’effet introuvable : utilisez film ou un identifiant de scène/plan.");
      f.effects.push(e);
      result = { effect_id: e.id };

      break;
    }
    case "remove_effect": {
      const n = f.effects.length;
      f.effects = f.effects.filter((e: Json) => e.id !== a.effect_id);
      if (f.effects.length === n) fail(`Effet introuvable : ${a.effect_id}`);
      break;
    }
    default:
      fail(`Opération inconnue : ${name}`);
  }
  return { film: f, result: { ok: true, ...result, ...(warnings.length ? { warnings } : {}) } };
}

export function summarizeFilm(f: Json): string {
  // The autonomous director MUST see what each shot illustrates. A summary
  // containing only scene counts causes arbitrary stock-media assignments.
  const scenes = (f.scenes ?? []).map((s: Json) => {
    const words = String(s.narration?.text || s.narrativeGoal || "");
    const shotDescriptions = (s.shots ?? []).slice(0,50).map((p:Json) => {
      const type = p.visualMode === "programmatic" ?
        `code[${p.visualSpec?.type??"texte"}]: "${String(p.visualText??"").slice(0,95)}"` :
        `média=${p.mediaRef??"AUCUN"} (vision ${p.visualEvidence?.verifiedBy==="vision_observation_v1"?"contrôlée":"NON CONTRÔLÉE"})`;
      return `    [${p.id}] ${p.inSec}-${p.outSec}s ${type}`;
    });
    return `  ${s.order}. [${s.id}] ${s.title} — ${s.durationSec}s, ${s.shots?.length ?? 0} plan(s)${s.mood ? `, ${s.mood}` : ""}
    Récit : ${words.slice(0,1200)}${words.length>1200?" …[utiliser get_film pour texte complet]":""}
${shotDescriptions.join("\n") || "    AUCUN PLAN"}`;
  });
  const total = (f.scenes ?? []).reduce((n: number, s: Json) => n + (s.durationSec ?? 0), 0);
  return [
    `Titre : ${f.info?.title} (type : ${f.info?.type}, langue : ${f.info?.language}, politique visuelle : ${f.info?.visualPolicy??"héritée"})`,
    `Format : ${f.format?.aspect} ${f.format?.width}x${f.format?.height} @${f.format?.fps}fps`,
    `Durée cumulée des scènes : ${total}s`,
    `Scènes (${f.scenes?.length ?? 0}) :${scenes.length ? "\n" + scenes.join("\n") : " aucune"}`,
    `Personnages : ${(f.characters ?? []).map((c: Json) => `${c.name} [${c.id}]`).join(", ") || "aucun"}`,
    `Médias dans le film : ${f.media?.length ?? 0} · pistes audio : ${f.audio?.tracks?.length ?? 0} · sous-titres : ${f.subtitles?.length ?? 0} · effets : ${f.effects?.length ?? 0}`,
  ].join("\n");
}

