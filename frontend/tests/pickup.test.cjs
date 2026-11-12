const test=require('node:test');
const assert=require('node:assert/strict');
const P=require('../../backend/static/pickup-data.js');
function storage(){let data={};return {getItem:k=>data[k]||null,setItem:(k,v)=>{data[k]=v;}};}
const point=(extra={})=>({id:'osm:N:123',marketplace:'Ozon',region_id:213,name:'Ozon',address:'Тверская улица 7, Москва',lat:55.75,lon:37.62,...extra});
test('choices survive reload and stay separate by marketplace and city',()=>{
  const s=storage();P.save(s,point());P.save(s,point({marketplace:'Яндекс Маркет',id:'osm:W:42'}));P.save(s,point({region_id:2,address:'Невский проспект'}));
  assert.equal(Object.keys(P.read(s)).length,3);
  P.remove(s,213,'Ozon');assert.equal(Object.keys(P.read(s)).length,2);assert.ok(P.read(s)[P.key(2,'Ozon')]);
});
test('corrupt storage and mismatched keys are ignored',()=>{
  const s=storage();s.setItem(P.KEY,'bad');assert.deepEqual(P.read(s),{});
  s.setItem(P.KEY,JSON.stringify({version:1,choices:{[P.key(2,'Ozon')]:point()}}));assert.deepEqual(P.read(s),{});
});
test('arbitrary text or invalid coordinates cannot be saved as a pickup point',()=>{
  for(const p of [point({id:'manual:address'}),point({lat:NaN}),point({lon:181}),point({marketplace:'Other'}),point({address:''})])assert.throws(()=>P.save(storage(),p));
});
test('address hints match words independently, case and punctuation are ignored',()=>{
  assert.equal(P.matches([point()],'москва тверская 7').length,1);
  assert.equal(P.matches([point({address:'Орёл, ул. Ленина 7'})],'орел ленина').length,1);
  assert.equal(P.matches([point()],'тверская 9').length,0);
});
test('storage failures reach the caller so UI cannot claim a successful save',()=>{
  assert.throws(()=>P.save({getItem:()=>null,setItem:()=>{throw Error('blocked');}},point()),/blocked/);
});
