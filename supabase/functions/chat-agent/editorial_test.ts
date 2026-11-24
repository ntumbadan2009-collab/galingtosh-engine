import { editorialTimelineIssues } from "./editorial.ts";
Deno.test("level three refuses uncovered or overlapping timeline", ()=>{
  const film={info:{editorialLevel:3},scenes:[{durationSec:6,shots:[{inSec:0,outSec:3},{inSec:3,outSec:6}]}]};
  if(editorialTimelineIssues(film).length)throw Error("valid timeline rejected");
  film.scenes[0].shots[1].inSec=4;
  if(!editorialTimelineIssues(film).length)throw Error("gap accepted");
  film.scenes[0].shots[1].inSec=2;
  if(!editorialTimelineIssues(film).length)throw Error("overlap accepted");
});
