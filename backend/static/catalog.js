(function (root) {
  "use strict";
  const validPrice = offer => Number.isFinite(Number(offer.price)) && Number(offer.price) > 0;
  const currency = offer => offer.currency || "RUB";
  function images(offer) {
    return [...new Set([offer.image_url, ...(Array.isArray(offer.image_urls) ? offer.image_urls : [])])]
      .filter(url => {
        try { const u = new URL(url); return u.protocol === "https:" && !u.username && !u.password; }
        catch { return false; }
      }).slice(0, 20);
  }
  function deliveryDays(offer, today = new Date()) {
    const d = offer.delivery || {};
    if (d.latest_date && /^\d{4}-\d{2}-\d{2}$/.test(d.latest_date)) {
      const end = new Date(d.latest_date + "T00:00:00");
      const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
      const days = Math.round((end - start) / 86400000);
      return Number.isFinite(days) && days >= 0 ? days : Infinity;
    }
    return typeof d.max_days === "number" && Number.isFinite(d.max_days) && d.max_days >= 0
      ? d.max_days : Infinity;
  }
  function deliveryLabel(offer) {
    const d = offer.delivery || {};
    let text = "Срок уточните в магазине";
    if (d.text) text = d.text;
    else if (d.latest_date) {
      const format = value => new Date(value + "T00:00:00").toLocaleDateString("ru-RU", {day:"numeric", month:"long"});
      if (deliveryDays(offer) !== Infinity) {
        text = d.earliest_date && d.earliest_date !== d.latest_date
          ? format(d.earliest_date) + " — " + format(d.latest_date) : format(d.latest_date);
      }
    } else if (typeof d.max_days === "number") {
      text = typeof d.min_days === "number" && d.min_days !== d.max_days
        ? d.min_days + "–" + d.max_days + " дн." : "До " + d.max_days + " дн.";
    }
    return (/^доставка(?:\s|:|$)/i.test(text) ? text : "Доставка: " + text) + (d.destination ? " · " + d.destination : "");
  }
  function bestOffers(offers) {
    const available = offers.filter(o => o.in_stock !== false && validPrice(o));
    const byCurrency = new Map();
    for (const o of available) {
      const group = byCurrency.get(currency(o)) || [];
      group.push(o); byCurrency.set(currency(o), group);
    }
    return new Set([...byCurrency.values()].flatMap(group => {
      if (group.length < 2) return [];
      const knownStock = group.filter(o => o.in_stock === true);
      const candidates = knownStock.length ? knownStock : group;
      const min = Math.min(...candidates.map(o => Number(o.price)));
      return candidates.filter(o => Number(o.price) === min);
    }));
  }
  function badges(offer, best) {
    const result = [];
    if (best?.has(offer)) result.push("Лучшее предложение");
    if (offer.in_stock !== false && deliveryDays(offer) <= 2) result.push("Быстрая доставка");
    if (Number(offer.rating) >= 4.5 && Number(offer.review_count) >= 10) result.push("Высокая оценка");
    return result;
  }
  function lowest(product, field, chosenCurrency) {
    const values = product.offers.filter(o => !chosenCurrency || currency(o) === chosenCurrency)
      .map(o => field === "delivery" ? o.in_stock === false ? Infinity : deliveryDays(o) : validPrice(o) ? Number(o.price) : Infinity);
    return Math.min(Infinity, ...values);
  }
  function filterProducts(products, filters = {}) {
    const hasPrice = filters.min !== "" && filters.min != null || filters.max !== "" && filters.max != null;
    const min = filters.min === "" || filters.min == null ? 0 : Number(filters.min);
    const max = filters.max === "" || filters.max == null ? Infinity : Number(filters.max);
    return products.flatMap(product => {
      const offers = product.offers.filter(offer => {
        if (filters.marketplace && offer.marketplace !== filters.marketplace) return false;
        if (filters.brand && offer.brand !== filters.brand) return false;
        if (filters.stock && offer.in_stock !== true) return false;
        if (filters.rating && Number(offer.rating || 0) < Number(filters.rating)) return false;
        if (filters.currency && currency(offer) !== filters.currency) return false;
        if (hasPrice && (!validPrice(offer) || Number(offer.price) < min || Number(offer.price) > max)) return false;
        if (filters.delivery && (offer.in_stock === false || deliveryDays(offer) === Infinity ||
            filters.delivery !== "known" && deliveryDays(offer) > Number(filters.delivery))) return false;
        return true;
      });
      return offers.length ? [{...product, offers, sourceOffers:product.offers}] : [];
    });
  }
  function sortProducts(products, order, chosenCurrency) {
    const list = [...products];
    if (order === "price-asc" || order === "price-desc") {
      const direction = order === "price-desc" ? -1 : 1;
      list.sort((a, b) => {
        const ap = lowest(a, "price", chosenCurrency), bp = lowest(b, "price", chosenCurrency);
        if (ap === Infinity || bp === Infinity) return ap === bp ? 0 : ap === Infinity ? 1 : -1;
        return (ap - bp) * direction;
      });
    } else if (order === "rating") {
      const score = p => Math.max(0, ...p.offers.map(o => Number(o.rating) || 0));
      list.sort((a,b) => score(b) - score(a));
    } else if (order === "delivery") {
      list.sort((a,b) => lowest(a,"delivery") - lowest(b,"delivery"));
    }
    return list;
  }
  const api = {images, currency, validPrice, deliveryDays, deliveryLabel, bestOffers, badges, filterProducts, sortProducts};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.MultiMarketCatalog = api;
})(typeof window === "undefined" ? globalThis : window);
