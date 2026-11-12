(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MultiMarketHistory = api;
})(typeof window === "undefined" ? globalThis : window, function () {
  "use strict";
  function normalize(points) {
    return (Array.isArray(points) ? points : []).filter(p => p && typeof p.price === "number" &&
      Number.isFinite(p.price) && p.price > 0 && /^[A-Z]{3}$/.test(p.currency) &&
      Number.isFinite(Date.parse(p.captured_at))).map(p => ({...p, time: Date.parse(p.captured_at)}))
      .sort((a, b) => a.time - b.time);
  }
  function change(previous, current) {
    if (!previous || !current || previous.currency !== current.currency || previous.price <= 0) return null;
    const amount = current.price - previous.price;
    return {amount, percent: amount / previous.price * 100, currency: current.currency};
  }
  function select(points, currency, days, now = Date.now()) {
    const cutoff = days ? now - Number(days) * 86400000 : -Infinity;
    return points.filter(p => p.currency === currency && p.time >= cutoff && p.time <= now);
  }
  function summary(points) {
    if (!points.length) return null;
    return {first: points[0], last: points.at(-1), change: points.length > 1 ? change(points[0], points.at(-1)) : null,
      min: Math.min(...points.map(p => p.price)), max: Math.max(...points.map(p => p.price))};
  }
  function layout(points, width = 760) {
    const left = 92, right = width - 20, top = 22, bottom = 226;
    const values = points.map(p => p.price), min = Math.min(...values), max = Math.max(...values);
    // Flat prices still need a useful, nonzero vertical range.
    const padding = Math.max((max - min) * .1, max * .01, .01);
    const roughStep = (max - min + 2 * padding) / 4;
    const power = 10 ** Math.floor(Math.log10(roughStep));
    const step = [1, 2, 2.5, 5, 10].find(n => n * power >= roughStep) * power;
    const low = Math.max(0, Math.floor((min - padding) / step) * step);
    const high = Math.ceil((max + padding) / step) * step;
    const ticks = Array.from({length: Math.round((high - low) / step) + 1}, (_, i) => low + i * step);
    const start = points[0].time, end = points.at(-1).time;
    const x = time => end === start ? (left + right) / 2 : left + (time - start) / (end - start) * (right - left);
    const y = price => bottom - (price - low) / (high - low) * (bottom - top);
    return {left, right, top, bottom, low, high, ticks, start, end, x, y,
      coordinates: points.map(p => ({x: x(p.time), y: y(p.price)}))};
  }
  return {normalize, change, select, summary, layout};
});
