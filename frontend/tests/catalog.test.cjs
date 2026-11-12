const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../../backend/static/catalog.js');
const offer = (extra = {}) => ({marketplace:'Ozon',price:100,currency:'RUB',in_stock:true,...extra});
test('all conditions must match the same offer, without mutating the original', () => {
  const products = [{title:'A',offers:[offer({price:50,in_stock:false}),offer({price:200})]}];
  assert.equal(C.filterProducts(products,{max:100,stock:true}).length,0);
  assert.equal(products[0].offers.length,2);
});
test('price comparisons stay in the selected currency', () => {
  const products = [{title:'A',offers:[offer({currency:'USD',price:1})]}, {title:'B',offers:[offer({price:90})]}];
  assert.deepEqual(C.filterProducts(products,{currency:'RUB'}).map(p=>p.title),['B']);
});
test('stock, brand, rating and marketplace filters can be combined', () => {
  const products = [{title:'A',offers:[offer({brand:'Sony',rating:4.8})]},{title:'B',offers:[offer({brand:'Sony'})]}];
  assert.deepEqual(C.filterProducts(products,{stock:true,brand:'Sony',marketplace:'Ozon',rating:4.5}).map(p=>p.title),['A']);
});
test('unknown and expired delivery dates do not qualify for fast delivery', () => {
  assert.equal(C.deliveryDays(offer()),Infinity);
  assert.equal(C.deliveryDays(offer({delivery:{latest_date:'2020-01-01'}}),new Date('2026-11-12')),Infinity);
  const products = [{offers:[offer()]},{offers:[offer({delivery:{max_days:3}})]}];
  assert.equal(C.filterProducts(products,{delivery:'3'}).length,1);
  assert.equal(C.filterProducts([{offers:[offer({in_stock:false,delivery:{max_days:1}})]}],{delivery:'3'}).length,0);
});
test('free delivery with unknown timing remains an unknown delivery time', () => {
  const o=offer({delivery:{cost:0,currency:'RUB'}});
  assert.equal(C.deliveryDays(o),Infinity);
  assert.match(C.deliveryLabel(o),/уточните/);
});
test('best offers exclude out of stock items and keep currencies separate', () => {
  const a=offer({price:50,in_stock:false}), b=offer({price:90}), c=offer({price:100}), usd=offer({price:1,currency:'USD'});
  assert.deepEqual([...C.bestOffers([a,b,c,usd])],[b]);
  assert.equal(C.bestOffers([b]).size,0);
});
test('recommendations prefer confirmed stock over unknown availability', () => {
  const a=offer({price:50,in_stock:null}), b=offer({price:90});
  assert.deepEqual([...C.bestOffers([a,b])],[b]);
});
test('sorts price and delivery without modifying the source list', () => {
  const a={title:'A',offers:[offer({price:200})]}, b={title:'B',offers:[offer({price:90,delivery:{max_days:2}})]};
  const list=[a,b];
  assert.deepEqual(C.sortProducts(list,'price-asc','RUB').map(p=>p.title),['B','A']);
  assert.deepEqual(C.sortProducts(list,'delivery','RUB').map(p=>p.title),['B','A']);
  assert.deepEqual(list.map(p=>p.title),['A','B']);
});
test('image galleries reject unsafe schemes, credentials and duplicates', () => {
  assert.deepEqual(C.images({image_url:'https://cdn.example/a',image_urls:['https://cdn.example/a','javascript:1','https://u:p@cdn.example/b','https://cdn.example/c']}),['https://cdn.example/a','https://cdn.example/c']);
});
test('high rating and fast delivery badges require supporting data', () => {
  assert.deepEqual(C.badges(offer({rating:5,review_count:1})),[]);
  assert.deepEqual(C.badges(offer({rating:4.8,review_count:10,delivery:{max_days:2}})),['Быстрая доставка','Высокая оценка']);
});
const futureDate = days => {
  const d = new Date();
  return new Date(Date.UTC(d.getFullYear(),d.getMonth(),d.getDate()+days)).toISOString().slice(0,10);
};
test('delivery filters use the last date in a range, not its first date', () => {
  const slow={title:'Range',offers:[offer({delivery:{earliest_date:futureDate(1),latest_date:futureDate(13)}})]};
  const fast={title:'Soon',offers:[offer({delivery:{earliest_date:futureDate(2),latest_date:futureDate(3)}})]};
  assert.deepEqual(C.filterProducts([slow,fast],{delivery:'3'}).map(p=>p.title),['Soon']);
  assert.deepEqual(C.sortProducts([slow,fast],'delivery').map(p=>p.title),['Soon','Range']);
});
test('known delivery accepts an explicit start but does not invent its upper bound', () => {
  const o=offer({delivery:{earliest_date:futureDate(2)}});
  assert.equal(C.hasDeliveryEstimate(o),true);
  assert.equal(C.deliveryDays(o),Infinity);
  assert.equal(C.filterProducts([{offers:[o]}],{delivery:'known'}).length,1);
  assert.equal(C.filterProducts([{offers:[o]}],{delivery:'3'}).length,0);
});
test('partial or stale delivery never qualifies as known or fast', () => {
  const partial=offer({delivery:{text:'В пути до 2 дней',partial:true,max_days:2}});
  const stale=offer({delivery:{text:'Завтра',latest_date:'2020-01-01',max_days:1}});
  assert.equal(C.hasDeliveryEstimate(partial),false);
  assert.equal(C.hasDeliveryEstimate(stale),false);
  assert.equal(C.filterProducts([{offers:[partial]},{offers:[stale]}],{delivery:'known'}).length,0);
});
test('relative wording from yesterday is displayed as its actual date', () => {
  const o=offer({delivery:{text:'Послезавтра, ПВЗ',earliest_date:'2026-11-14',latest_date:'2026-11-14',method:'Пункт выдачи'}});
  const label=C.deliveryLabel(o,new Date(2026,10,13));
  assert.match(label,/14 ноября/);
  assert.doesNotMatch(label,/Послезавтра/);
  assert.match(label,/Пункт выдачи/);
  assert.match(C.deliveryLabel(o,new Date(2026,10,15)),/устарел/);
});
test('invalid ISO dates are rejected instead of overflowing into a later month', () => {
  assert.equal(C.deliveryDays(offer({delivery:{latest_date:'2027-02-31'}}),new Date(2027,1,1)),Infinity);
});
