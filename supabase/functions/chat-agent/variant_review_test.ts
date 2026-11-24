import {parseVariantReview,selectVariant,selectionWinner,applyTrialSelection} from "./variant_review.ts";
const p={relevance:"pass",readability:"pass",composition:"pass",observation:"Objet visible et texte lisible."};
function row(shotId:string,preference:string,A:any=p,B:any=p){return {shotId,A,B,preference,reason:"Comparaison des deux images."};}
Deno.test("only consistent relevant visual preference, not invented ranking",()=>{
 const parse=(r:any[])=>parseVariantReview(JSON.stringify(r),r.map(x=>x.shotId));
 if(selectVariant(parse([row("s1","A"),row("s2","A")])).winner!=="A")throw Error("valid preference rejected");
 for(const r of [[row("s1","tie")],[row("s1","A"),row("s2","B")],[row("s1","A",{...p,relevance:"fail"})],[row("s1","B",{...p,composition:"uncertain"})]])if(selectVariant(parse(r)).winner!==null)throw Error("unsafe winner");
 let refused=false;try{parseVariantReview(JSON.stringify([row("s1","A")]),["s2"])}catch{refused=true}
 if(!refused)throw Error("wrong shot accepted");
});

Deno.test("selection rejects a verdict that disagrees with the independent review",()=>{
 const rows=parseVariantReview(JSON.stringify([row("s1","B")]),["s1"]);
 const result={...selectVariant(rows),manifestSha256:"a".repeat(64),candidateHashes:{A:"b".repeat(64),B:"c".repeat(64)},rows,usage:{input:1,output:1},limitations:"fixture"};
 if(selectionWinner(result)!=="B")throw Error("expected B");
 let refused=false;try{selectionWinner({...result,winner:"A"})}catch{refused=true}
 if(!refused)throw Error("forged winner accepted");
 const tied=parseVariantReview(JSON.stringify([row("s1","tie")]),["s1"]);
 if(selectionWinner({...result,...selectVariant(tied),rows:tied})!==null)throw Error("tie applied");
});
Deno.test("abstention does not read or write any files",async()=>{
 const rows=parseVariantReview(JSON.stringify([row("s1","tie")]),["s1"]);
 const result=await applyTrialSelection("/nonexistent-private-trial",{...selectVariant(rows),manifestSha256:"a".repeat(64),candidateHashes:{},rows,usage:{input:1,output:1},limitations:"fixture"});
 if(result.status!=="needs_review"||result.winner!==null)throw Error("abstention ignored");
});
