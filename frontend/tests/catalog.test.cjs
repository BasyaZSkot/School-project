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
