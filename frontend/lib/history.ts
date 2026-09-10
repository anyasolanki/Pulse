export type Observation={event_id:string;story_id:number|string;title:string;observed_at:string;score:number|string;comments:number|string};
export function epoch(value:string){return new Date(value.includes('T')?value:value.replace(' ','T')+'Z').getTime()}
export function segments(rows:Observation[],metric:'score'|'comments'){
 const sorted=[...new Map(rows.map(row=>[row.event_id,row])).values()].sort((a,b)=>epoch(a.observed_at)-epoch(b.observed_at));
 const lines:{x:number;y:number}[][]=[];const gaps:{from:number;to:number}[]=[];
 for(const row of sorted){const point={x:epoch(row.observed_at),y:Number(row[metric])};if(!Number.isFinite(point.x)||!Number.isFinite(point.y))continue;
 const last=lines.at(-1)?.at(-1);if(!last||point.x-last.x>180000){if(last)gaps.push({from:last.x,to:point.x});lines.push([])}lines.at(-1)!.push(point)}
 return {lines,gaps};
}
