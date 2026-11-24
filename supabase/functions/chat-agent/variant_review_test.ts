import {parseVariantReview,selectVariant} from "./variant_review.ts";
const p={relevance:"pass",readability:"pass",composition:"pass",observation:"Objet visible et texte lisible."};
function row(shotId:string,preference:string,A:any=p,B:any=p){return {shotId,A,B,preference,reason:"Comparaison des deux images."};}
Deno.test("only consistent relevant visual preference, not invented ranking",()=>{
 const parse=(r:any[])=>parseVariantReview(JSON.stringify(r),r.map(x=>x.shotId));
 if(selectVariant(parse([row("s1","A"),row("s2","A")])).winner!=="A")throw Error("valid preference rejected");
 for(const r of [[row("s1","tie")],[row("s1","A"),row("s2","B")],[row("s1","A",{...p,relevance:"fail"})],[row("s1","B",{...p,composition:"uncertain"})]])if(selectVariant(parse(r)).winner!==null)throw Error("unsafe winner");
 let refused=false;try{parseVariantReview(JSON.stringify([row("s1","A")]),["s2"])}catch{refused=true}
 if(!refused)throw Error("wrong shot accepted");
});
