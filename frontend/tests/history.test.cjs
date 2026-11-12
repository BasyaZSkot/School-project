const test = require('node:test');
const assert = require('node:assert/strict');
const H = require('../../backend/static/history-data.js');
const p = (price, day, currency='RUB') => ({price,currency,captured_at:`2026-11-${String(day).padStart(2,'0')}T12:00:00Z`});
test('history ignores invalid values and orders checks chronologically', () => {
  const points = H.normalize([p(90,12),p(100,1),p(Infinity,3),p(0,4),{...p(20,2),captured_at:'bad'}]);
  assert.deepEqual(points.map(p=>p.price),[100,90]);
});
test('change shows amount and percentage relative to the earlier price', () => {
  assert.deepEqual(H.change(p(200,1),p(150,2)),{amount:-50,percent:-25,currency:'RUB'});
  assert.equal(H.change(p(100,1),p(200,2)).percent,100);
  assert.equal(H.change(p(100,1),p(100,2)).amount,0);
  assert.equal(H.change(p(100,1),p(50,2,'USD')),null);
  assert.equal(H.summary(H.normalize([p(100,1)])).change,null);
});
test('period and currency filter cannot mix currencies or include future data', () => {
  const now=Date.parse('2026-11-12T12:00:00Z');
  const points=H.normalize([p(300,1),p(200,7),p(2,8,'USD'),p(150,12),p(1,13)]);
  const selected=H.select(points,'RUB',7,now),summary=H.summary(selected);
  assert.deepEqual(selected.map(p=>p.price),[200,150]);
  assert.equal(summary.change.amount,-50);assert.equal(summary.change.percent,-25);
  assert.equal(summary.min,150);assert.equal(summary.max,200);
  assert.equal(H.summary([]),null);
});
test('chart spaces checks by elapsed time rather than by check count', () => {
  const g=H.layout(H.normalize([p(100,1),p(90,2),p(80,11)]));
  const [a,b,c]=g.coordinates;
  assert.ok(Math.abs((b.x-a.x)/(c.x-a.x)-.1)<1e-8);
});
test('flat prices and simultaneous checks have finite centred coordinates', () => {
  const g=H.layout(H.normalize([p(100,1),p(100,1)]),320);
  assert.ok(g.low<100 && g.high>100);
  assert.ok(g.coordinates.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
  assert.equal(g.coordinates[0].x,(g.left+g.right)/2);
});
