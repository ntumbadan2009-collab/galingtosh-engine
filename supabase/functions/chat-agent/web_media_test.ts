import {archiveCandidates,publicLicense,webReferences,httpsUrl,safeMetadata,smithsonianCandidates} from "./web_media.ts";
function check(x:unknown){if(!x)throw Error("assertion failed");}
Deno.test("strict license URL and unknown/NC/ND rejection",()=>{
 check(publicLicense("https://creativecommons.org/licenses/by/4.0/")?.license==="CC BY 4.0");
 for(const s of ["https://evil.example/licenses/by/4.0/","https://creativecommons.org/licenses/by-nc/4.0/","https://creativecommons.org/licenses/by-nd/4.0/","https://creativecommons.org.evil.example/licenses/by/4.0/"])check(publicLicense(s)===null);
});
Deno.test("search refs are non-importable and block obvious harmful metadata",()=>{
 const rows=webReferences({results:[{url:"https://example.com/article",title:"Press release",page_age:"2026-11-23"},{url:"https://pornhub.com/a",title:"Other"},{url:"https://example.com/b",title:"NSFW"},{url:"http://example.com/a",title:"Old"}]},"news");
 check(rows.length===1&&rows[0].importable===false&&rows[0].published==="2026-11-23");
 check(!httpsUrl("https://127.0.0.1/a"));check(!httpsUrl("https://a.local/a"));check(!httpsUrl("https://user:pass@example.org/a"));check(!safeMetadata("gore"));
});
Deno.test("archive rejects active or oversized files and unknown rights",()=>{
 const item={metadata:{identifier:"test",title:"Nature",creator:"Author",licenseurl:"https://creativecommons.org/licenses/by/4.0/"},files:[{name:"payload.html",size:30,format:"HTML"},{name:"huge.mp4",size:999999999,format:"MPEG4"},{name:"safe.mp4",size:3000,format:"MPEG4"}]};
 check(archiveCandidates(item,"video").length===1);
 check(archiveCandidates({...item,metadata:{...item.metadata,licenseurl:""}}, "video").length===0);
});
Deno.test("Smithsonian uses per-asset CC0 and never returns the Voyager URL",()=>{
 const raw={response:{rows:[{id:"test",title:"Specimen",content:{descriptiveNonRepeating:{online_media:{media:[{type:"3d_voyager",usage:{access:"CC0"},content:"https://3d-api.si.edu/voyager/abc",thumbnail:"https://3d-api.si.edu/content/abc.jpg"},{type:"Images",usage:{access:"Usage conditions apply"},content:"https://ids.si.edu/test"}]}}}}]}};
 const r=smithsonianCandidates(raw,5);check(r.length===1&&r[0].kind==="image"&&r[0].download_url.endsWith(".jpg"));
});

import {institutionalReference} from "./web_media.ts";
Deno.test("quarantined institutional references cannot be attached or downloaded directly",()=>{
 const ref=institutionalReference({source:"archive",title:"Nature",kind:"video",url:"https://archive.org/details/sample",id:"archive:sample",download_url:"https://archive.org/download/sample/movie.mp4",license:"CC BY 4.0"});
 check(ref?.importable===false&&ref?.source==="archive"&&!("id" in ref!)&&!("download_url" in ref!));
 check(institutionalReference({source:"archive",title:"NSFW",kind:"video",url:"https://archive.org/details/sample"})===null);
});
