import {applyOperation,defaultFilm} from './film.ts';
const assert=(v:unknown)=>{if(!v)throw new Error('Assertion failed');};
Deno.test('default film and edits remain immutable',()=>{
 const before=defaultFilm('Test');const {film}=applyOperation(before,'add_scene',{title:'Scene',narrativeGoal:'Test',durationSec:5});
 assert(before.scenes.length===0);assert(film.scenes.length===1);
});
Deno.test('new TTS uses supported engine contract',()=>{
 const {film}=applyOperation(defaultFilm('Test'),'add_audio_track',{kind:'voiceover',tts:{text:'Bonjour'}});
 assert(film.audio.tracks[0].tts.provider==='edge-tts');
});
Deno.test('unsupported render resolution and effects are rejected',()=>{
 for(const [name,args] of [['set_render_params',{resolution:'4k'}],['add_effect',{type:'invented',target:'film'}]] as const){
  let rejected=false;try{applyOperation(defaultFilm('Test'),name,args);}catch{rejected=true;}assert(rejected);
 }
});
Deno.test('title alias maps to implemented overlay',()=>{
 const {film}=applyOperation(defaultFilm('Test'),'add_effect',{type:'title_overlay',target:'film',params:{text:'Bonjour'}});
 assert(film.effects[0].type==='text_overlay');
});

Deno.test('source video offsets are saved and can be edited independently of scene timing',()=>{
 const first=applyOperation(defaultFilm('Source'), 'add_scene', {title:'Savane', narrativeGoal:'Lion',durationSec:8}).film;
 const sceneId=first.scenes[0].id;
 const second=applyOperation(first,'add_shot',{scene_id:sceneId,inSec:1,outSec:5,sourceInSec:42}).film;
 const shot=second.scenes[0].shots[0];
 assert(shot.sourceInSec===42 && shot.inSec===1 && shot.outSec===5);
 const revised=applyOperation(second,'update_shot',{shot_id:shot.id,sourceInSec:65}).film;
 assert(revised.scenes[0].shots[0].sourceInSec===65);
 assert(revised.scenes[0].shots[0].inSec===1);
 assert(second.scenes[0].shots[0].sourceInSec===42);
});
Deno.test('negative source offsets are rejected',()=>{
 const first=applyOperation(defaultFilm('Source'),'add_scene',{title:'Savane',narrativeGoal:'Lion',durationSec:8}).film;
 let rejected=false;
 try{applyOperation(first,'add_shot',{scene_id:first.scenes[0].id,outSec:4,sourceInSec:-1});}catch{rejected=true;}
 assert(rejected);
});
