// Web references are discovery only: search results never establish reuse rights.
export type WebReference={title:string;url:string;published?:string;kind:string;importable:false};
const adult=/\b(?:porn(?:ography|hub|ographique)?|xxx|nsfw|hentai|gore|snuff|nude|nudity|pornographie|nudité|décapitation|torture|sexually explicit)\b/iu;
const badHost=/(?:^|[.-])(?:pornhub|xvideos|xnxx|xhamster|redtube|onlyfans|youporn|rule34)(?:[.-]|$)/i;
export function safeMetadata(...values:unknown[]):boolean{
 return values.every(v=>typeof v!=="string"||(!adult.test(v)&&!badHost.test(v)));
}
export function httpsUrl(value:unknown):string|null{
 try{if(typeof value!=="string"||value.length>2048)return null;const u=new URL(value);
 if(u.protocol!=="https:"||u.username||u.password||u.port||!u.hostname.includes(".")||/^\d|^\[|(?:^|\.)(?:localhost|local|internal|lan)$/.test(u.hostname)||!safeMetadata(u.hostname,u.pathname))return null;
 u.hash="";return u.toString();}catch{return null;}
}
export function publicLicense(value:unknown):{license:string;license_url:string}|null{
 if(typeof value!=="string")return null;
 try{const u=new URL(value);if(!["creativecommons.org","www.creativecommons.org"].includes(u.hostname)||!["https:","http:"].includes(u.protocol)||u.username||u.password||u.port)return null;
 const m=u.pathname.match(/^\/(?:licenses\/(by)\/(4\.0|3\.0|2\.5|2\.0|1\.0)|publicdomain\/(zero|mark)\/(1\.0))\/?$/);
 if(!m)return null;return {license:m[1]?"CC BY "+m[2]:m[3]==="zero"?"CC0 1.0":"Public Domain Mark 1.0",license_url:"https://creativecommons.org"+u.pathname.replace(/\/?$/,"/")};}catch{return null;}
}
async function json(u:URL,headers:Record<string,string>={}){
 const r=await fetch(u,{headers:{Accept:"application/json",...headers},redirect:"error",signal:AbortSignal.timeout(7000)});
 if(!r.ok)throw Error("HTTP "+r.status);const reader=r.body?.getReader();if(!reader)throw Error("missing body");
 let total=0;const chunks:Uint8Array[]=[];try{for(;;){const {done,value}=await reader.read();if(done)break;total+=value.length;if(total>2_000_000)throw Error("oversize metadata");chunks.push(value);}}finally{await reader.cancel().catch(()=>{});}
 const out=new Uint8Array(total);let offset=0;for(const c of chunks){out.set(c,offset);offset+=c.length;}
 return JSON.parse(new TextDecoder().decode(out));
}
export function webReferences(raw:any,kind:string):WebReference[]{
 return (Array.isArray(raw?.results)?raw.results:[]).flatMap((r:any)=>{
 const url=httpsUrl(r.url);const title=typeof r.title==="string"?r.title.slice(0,300):"";
 if(!url||!title||!safeMetadata(title,r.description,url))return [];
 return [{title,url,published:typeof r.age==="string"?r.age:typeof r.page_age==="string"?r.page_age:undefined,kind,importable:false as const}];});
}
export async function discoverWeb(query:string,kind:string,key:string,limit:number):Promise<WebReference[]>{
 if(!safeMetadata(query))return [];
 const route=kind==="video"?"videos/search":kind==="news"?"news/search":kind==="model3d"?"web/search":"images/search";
 const u=new URL("https://api.search.brave.com/res/v1/"+route);
 u.searchParams.set("q",kind==="model3d"?query+" CC0 3D model":query);
 u.searchParams.set("safesearch","strict");u.searchParams.set("count",String(Math.min(20,limit)));
 if(kind==="news")u.searchParams.set("freshness","pm");
 const raw=await json(u,{"X-Subscription-Token":key});return webReferences(route==="web/search"?raw.web:raw,kind);
}
// Official museum API: only asset records explicitly marked public domain.
export async function artInstitute(query:string,limit:number){
 const u=new URL("https://api.artic.edu/api/v1/artworks/search");u.searchParams.set("q",query);u.searchParams.set("limit",String(limit));
 u.searchParams.set("fields","id,title,artist_display,image_id,is_public_domain,date_display");
 const raw=await json(u);
 return (raw.data??[]).flatMap((r:any)=>{
 if(r.is_public_domain!==true||!Number.isInteger(r.id)||typeof r.image_id!=="string"||!/^[a-f0-9-]{36}$/i.test(r.image_id)||!r.artist_display||!safeMetadata(r.title,r.artist_display))return [];
 const url="https://www.artic.edu/artworks/"+r.id;
 return [{id:"artic:"+r.id,source:"artic",kind:"image",title:String(r.title),author:String(r.artist_display),license:"CC0 1.0",license_url:"https://creativecommons.org/publicdomain/zero/1.0/",url,download_url:"https://www.artic.edu/iiif/2/"+r.image_id+"/full/843,/0/default.jpg",attribution:String(r.artist_display)+" — Art Institute of Chicago — "+url}];});
}
// Archive metadata is an uploader assertion, not independent proof. Reject unclear
// records and active formats; additional review before public release is required.
export function archiveCandidates(item:any,kind:string){
 const m=item?.metadata??{},id=m.identifier;
 const rights=publicLicense(m.licenseurl);const author=typeof m.creator==="string"?m.creator:"";
 if(!rights||!author||typeof id!=="string"||!/^[A-Za-z0-9_.-]{1,120}$/.test(id)||m.access_restricted_item===true||m.access_restricted_item==="true"||!safeMetadata(id,m.title,author,m.description,JSON.stringify(m.subject??"")))return [];
 const url="https://archive.org/details/"+encodeURIComponent(id);const max=kind==="video"?45*1024*1024:12*1024*1024;
 const options=(item.files??[]).filter((f:any)=>typeof f.name==="string"&&/^[^/\\\x00-\x1f]{1,200}$/.test(f.name)&&!f.name.startsWith(".")&&Number(f.size)>0&&Number(f.size)<=max&&safeMetadata(f.name)&&(kind==="video"?/\.mp4$/i.test(f.name)&&/mpeg4|h\.264/i.test(String(f.format)):/\.(jpg|jpeg|png|webp)$/i.test(f.name)&&/jpeg|png|webp/i.test(String(f.format))));
 return options.slice(0,1).map((f:any)=>({id:"archive:"+id+":"+f.name,source:"archive",kind,title:String(m.title??id).slice(0,300),author,...rights,url,download_url:"https://archive.org/download/"+encodeURIComponent(id)+"/"+encodeURIComponent(f.name),size_bytes:Number(f.size),attribution:author+" — "+rights.license+" — "+url,published_at:typeof m.date==="string"?m.date:undefined}));
}
export async function archiveSearch(query:string,kind:string,limit:number){
 if(!safeMetadata(query))return [];
 const u=new URL("https://archive.org/advancedsearch.php");
 const terms=query.replace(/[^\p{L}\p{N} ._-]/gu," ").trim().slice(0,160);if(!terms)return [];
 u.searchParams.set("q","("+terms+") AND mediatype:"+(kind==="video"?"movies":"image")+" AND licenseurl:*");u.searchParams.set("fl[]","identifier");u.searchParams.set("rows",String(Math.min(6,limit)));u.searchParams.set("output","json");
 const raw=await json(u);
 const items=await Promise.allSettled((raw.response?.docs??[]).slice(0,6).map((r:any)=>typeof r.identifier==="string"&&/^[A-Za-z0-9_.-]{1,120}$/.test(r.identifier)?json(new URL("https://archive.org/metadata/"+encodeURIComponent(r.identifier))):Promise.resolve(null)));
 return items.flatMap(r=>r.status==="fulfilled"?archiveCandidates(r.value,kind):[]).slice(0,limit);
}
export const extendedSource=(source:unknown)=>source==="artic"||source==="archive";
export const extendedEnabled=()=>Deno.env.get("SECURE_WEB_MEDIA_ENABLED")==="true";
