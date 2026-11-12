(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MultiMarketPickupData = api;
})(typeof window === "undefined" ? globalThis : window, function () {
  "use strict";
  const KEY = "multimarket.pickup.v1", markets = ["Яндекс Маркет", "Ozon", "Wildberries"];
  const normalize = value => String(value || "").toLocaleLowerCase("ru").replace(/ё/g,"е").replace(/[^a-zа-я0-9]/g,"");
  const key = (region, market) => region + ":" + market;
  function valid(point) {
    return point && /^osm:[NWR]:[1-9]\d{0,15}$/.test(point.id) && markets.includes(point.marketplace) &&
      Number.isInteger(point.region_id) && point.region_id > 0 && point.region_id <= 1000000 &&
      typeof point.address === "string" && point.address.length > 0 && point.address.length <= 500 &&
      typeof point.name === "string" && point.name.length <= 200 &&
      Number.isFinite(point.lat) && Math.abs(point.lat) <= 85 && Number.isFinite(point.lon) && Math.abs(point.lon) <= 180;
  }
  function read(storage) {
    try {
      const value = JSON.parse(storage.getItem(KEY));
      if (value?.version !== 1 || !value.choices || typeof value.choices !== "object") return {};
      return Object.fromEntries(Object.entries(value.choices).slice(0,180).filter(([k,p]) => valid(p) && k === key(p.region_id,p.marketplace)));
    } catch { return {}; }
  }
  function save(storage, point) {
    if (!valid(point)) throw new Error("Выберите пункт из списка или на карте.");
    const choices = read(storage);
    choices[key(point.region_id,point.marketplace)] = {id:point.id,marketplace:point.marketplace,region_id:point.region_id,name:point.name,address:point.address,lat:point.lat,lon:point.lon};
    storage.setItem(KEY, JSON.stringify({version:1,choices}));
  }
  function remove(storage, region, market) {
    const choices = read(storage); delete choices[key(region,market)];
    storage.setItem(KEY, JSON.stringify({version:1,choices}));
  }
  function matches(points, query) {
    const words = String(query || "").trim().split(/\s+/).map(normalize).filter(Boolean);
    return points.filter(p => words.every(word => normalize(p.address + " " + p.name).includes(word)));
  }
  return {KEY,markets,key,valid,read,save,remove,matches};
});
