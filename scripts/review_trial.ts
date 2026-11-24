// Run locally on a private trial directory. Provider credentials are never stored.
import {reviewTrial} from "../supabase/functions/chat-agent/variant_review.ts";
import type {LlmCfg} from "../supabase/functions/chat-agent/llm.ts";
const directory=Deno.args[0],priority=Deno.args[1]??"Clarté et pertinence de la narration.";
const provider=Deno.env.get("LLM_PROVIDER"),key=Deno.env.get("LLM_API_KEY"),model=Deno.env.get("LLM_MODEL");
if(!directory||!key||!model||(provider!=="openai"&&provider!=="anthropic"))throw Error("Configuration et dossier privé requis.");
const cfg:LlmCfg={provider,key,model,base:(Deno.env.get("LLM_BASE_URL")??(provider==="openai"?"https://api.openai.com/v1":"https://api.anthropic.com")).replace(/\/$/,"")};
const result=await reviewTrial(cfg,directory,priority);
await Deno.writeTextFile(directory+"/visual_recommendation.json",JSON.stringify(result,null,2),{createNew:true});
console.log(result.status);
