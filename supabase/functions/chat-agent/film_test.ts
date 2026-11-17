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
