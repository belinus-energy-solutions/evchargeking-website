// evck-shop — checkout service of the EVChargeking webshop (Supabase project "Belinus Portal").
//
//   POST /quote            { country, buyer, vat, deliv, items:[{pid,sel,qty}] }      -> lines and totals (server prices)
//   POST /vat-check        { country, vat }                                           -> { valid: true|false|null } (EU VIES)
//   POST /order            quote fields + { customer, pay, lang, terms }              -> { number, token, checkoutUrl }
//   GET  /status?o=TOKEN                                                              -> order status for the confirmation page
//   POST /simulate         { token, result }                                          -> test payments when no Mollie key is set
//   POST /mollie-webhook   (called by Mollie)                                         -> updates the order from Mollie
//
// Prices never come from the browser: every order is priced here from the published catalogue.
//
// Secrets (Supabase > Edge Functions > Secrets):
//   MOLLIE_API_KEY    Mollie key. Without it the service runs its own payment simulator.
//                     A live key ("live_...") is REFUSED unless EVCK_ALLOW_LIVE=1, so the preview can never take real money.
//   EVCK_ALLOW_LIVE   set to 1 only at go-live.
// Not done here yet: order in Odoo, e-mails (Mailgun), portal account. Hooks are marked TODO in onPaid().
// Deploy with verify_jwt = false (public endpoint; it does its own validation).
import { createClient } from "npm:@supabase/supabase-js@2";

// The catalogue (products, VAT rates, delivery prices, promotion) is published with the site as /assets/shop-catalog.json
// by _src/app/build.py, so the pages and this service always use the same figures. Cached for five minutes.
type Cat = { products: Record<string, { p: number; n: string; w: number; a: { l: string; x: number }[][] }>; baseVat: number; vat: Record<string, number>; eu: string[]; ship: Record<string, { home: number | null; pickup: number | null }>; freeShip: { countries: string[]; over: number }; promo: { pid: number; pct: number; until: string } };
const CATALOG_URL = Deno.env.get("EVCK_CATALOG_URL") || "https://evchargeking-website.b-cdn.net/assets/shop-catalog.json";
let CAT: Cat | null = null, catAt = 0;
async function cat(): Promise<Cat> {
  if (CAT && Date.now() - catAt < 300000) return CAT;
  const r = await fetch(CATALOG_URL, { signal: AbortSignal.timeout(8000) }); if (!r.ok) { if (CAT) return CAT; throw new Error("catalogue " + r.status); }
  CAT = await r.json(); catAt = Date.now(); return CAT!;
}
const vatFormat = (country: string, vat: string) => new RegExp("^" + (country === "GR" ? "EL" : country) + "[0-9A-Z+*]{2,13}$").test(vat);

const ORIGINS = ["https://evchargeking-website.b-cdn.net", "https://evchargeking.com", "https://www.evchargeking.com", "http://127.0.0.1:8766", "http://localhost:8766"];
const LANGS = ["nl", "fr", "en", "es", "de", "it", "pt"];
const MOLLIE = Deno.env.get("MOLLIE_API_KEY") || "";
const ALLOW_LIVE = Deno.env.get("EVCK_ALLOW_LIVE") === "1";
const FN_URL = `${Deno.env.get("SUPABASE_URL")}/functions/v1/evck-shop`;
const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });

const cors = (req: Request) => {
  const o = req.headers.get("origin") || "";
  return { "Access-Control-Allow-Origin": ORIGINS.includes(o) ? o : ORIGINS[0], "Vary": "Origin", "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS" };
};
const json = (req: Request, o: unknown, status = 200) => new Response(JSON.stringify(o), { status, headers: { ...cors(req), "content-type": "application/json", "cache-control": "no-store" } });
class Bad extends Error { code: string; constructor(code: string, msg?: string) { super(msg || code); this.code = code; } }
const r2 = (n: number) => Math.round((n + Number.EPSILON) * 100) / 100;
const str = (v: unknown, max = 200) => String(v ?? "").trim().slice(0, max);

// ---------- pricing (same rules as the pages) ----------
function gross(C: Cat, pid: number, sel: number[]) {
  const PROMO = C.promo, promoOn = pid === PROMO.pid && new Date() <= new Date(PROMO.until + "T23:59:59+01:00");
  const p = C.products[pid]; if (!p) throw new Bad("unknown_product");
  let g = p.p; const opts: string[] = [];
  p.a.forEach((vals, i) => { const v = vals[Number(sel?.[i] ?? 0)]; if (!v) throw new Bad("unknown_option"); g += v.x || 0; opts.push(v.l); });
  const full = g; if (promoOn) g = Math.round(g * (100 - PROMO.pct)) / 100;
  return { gross: g, full, opts };
}
type Item = { pid: number; sel: number[]; qty: number };
async function viesValid(country: string, vat: string): Promise<boolean | null> {
  const cc = country === "GR" ? "EL" : country, num = vat.replace(/^[A-Z]{2}/, "");
  try {
    const r = await fetch(`https://ec.europa.eu/taxation_customs/vies/rest-api/ms/${cc}/vat/${encodeURIComponent(num)}`, { signal: AbortSignal.timeout(8000) });
    if (!r.ok) return null; const j = await r.json();
    if (typeof j.isValid === "boolean" && (j.userError === "VALID" || j.userError === "INVALID" || !j.userError)) return j.isValid;
    return null;                                   // member state service unavailable, etc.
  } catch { return null; }
}
async function quote(b: any, opts: { checkVat?: boolean } = {}) {
  const C = await cat(), SHIP = C.ship, VAT = C.vat, EU = new Set(C.eu), BASE_VAT = C.baseVat, FREE = new Set(C.freeShip.countries);
  const country = str(b.country, 2).toUpperCase(); if (!SHIP[country]) throw new Bad("country");
  const buyer = b.buyer === "company" ? "company" : "private";
  const items: Item[] = (Array.isArray(b.items) ? b.items : []).slice(0, 40).map((i: any) => ({ pid: Number(i.pid), sel: (Array.isArray(i.sel) ? i.sel : []).map(Number), qty: Math.max(1, Math.min(50, Math.floor(Number(i.qty) || 1))) }));
  if (!items.length) throw new Bad("empty");
  const vat = str(b.vat, 20).replace(/[\s.\-]/g, "").toUpperCase();
  let vatState: "none" | "format" | "valid" | "invalid" | "unverified" = "none";
  if (buyer === "company" && vat) {
    if (!vatFormat(country, vat)) vatState = "invalid";
    else if (!opts.checkVat) vatState = "format";
    else { const v = await viesValid(country, vat); vatState = v === true ? "valid" : v === false ? "invalid" : "unverified"; }
  }
  // 0% only outside the EU (export) or for an EU company outside Belgium whose VAT number VIES confirmed
  const reverse = buyer === "company" && country !== "BE" && EU.has(country) && (vatState === "valid" || (!opts.checkVat && vatState === "format"));
  const rate = !EU.has(country) ? 0 : reverse ? 0 : VAT[country];
  const lines = items.map((it) => { const g = gross(C, it.pid, it.sel); const ex = g.gross / BASE_VAT; return { pid: it.pid, name: C.products[it.pid].n, options: g.opts, qty: it.qty, unitEx: ex, lineEx: ex * it.qty, promo: g.full !== g.gross }; });
  const sub = lines.reduce((a, l) => a + l.lineEx, 0);
  const rates = SHIP[country]; let deliv = b.deliv === "pickup" ? "pickup" : "home"; if (rates[deliv as "home" | "pickup"] == null) deliv = rates.home != null ? "home" : "pickup";
  let ship = rates[deliv as "home" | "pickup"] ?? 0;
  const goods = sub * (1 + (EU.has(country) ? VAT[country] : 0) / 100);
  const free = FREE.has(country) && goods >= C.freeShip.over - 0.005; if (free) ship = 0;
  const ex = sub + ship, vatAmt = ex * rate / 100;
  return { country, buyer, vat, vatState, reverse, eu: EU.has(country), deliv, rate, lines: lines.map((l) => ({ ...l, unitEx: r2(l.unitEx), lineEx: r2(l.lineEx) })), sub: r2(sub), ship: r2(ship), free, vatAmount: r2(vatAmt), total: r2(ex + vatAmt), currency: "EUR" };
}

// ---------- orders ----------
const hex = (n: number) => [...crypto.getRandomValues(new Uint8Array(n))].map((b) => b.toString(16).padStart(2, "0")).join("");
function orderNumber() { const d = new Date().toISOString().slice(2, 10).replace(/-/g, ""); return `EVT${d}-${String(Math.floor(1000 + Math.random() * 9000))}`; }
const PAYMAP: Record<string, string> = { card: "creditcard", bancontact: "bancontact", ideal: "ideal", paypal: "paypal", applepay: "applepay", klarna: "klarna", transfer: "banktransfer", eps: "eps", twint: "twint", blik: "blik", p24: "przelewy24", trustly: "trustly", satispay: "satispay", mobilepay: "mobilepay" };
const MLOCALE: Record<string, string> = { nl: "nl_BE", fr: "fr_BE", en: "en_GB", es: "es_ES", de: "de_DE", it: "it_IT", pt: "pt_PT" };

async function mollie(path: string, init: RequestInit = {}) {
  const r = await fetch("https://api.mollie.com/v2" + path, { ...init, headers: { authorization: `Bearer ${MOLLIE}`, "content-type": "application/json", ...(init.headers || {}) }, signal: AbortSignal.timeout(15000) });
  const j = await r.json().catch(() => ({})); return { ok: r.ok, status: r.status, j };
}
async function addEvent(id: string, ev: Record<string, unknown>) {
  const { data } = await db.from("evck_orders").select("events").eq("id", id).single();
  await db.from("evck_orders").update({ events: [...((data?.events as unknown[]) || []), { at: new Date().toISOString(), ...ev }] }).eq("id", id);
}
async function setStatus(o: any, status: string, extra: Record<string, unknown> = {}) {
  if (o.status === status) return;
  if (o.status === "paid") return;                    // a paid order never goes back
  await db.from("evck_orders").update({ status, ...(status === "paid" ? { paid_at: new Date().toISOString() } : {}), ...extra }).eq("id", o.id);
  await addEvent(o.id, { status });
  if (status === "paid") await onPaid(o);
}
async function onPaid(o: any) {
  // TODO (next steps, each needs its own secret): create the order in the EVChargeking Odoo, send the confirmation
  // e-mail through Mailgun, create the customer's account in the service portal. Until then the order is only stored here.
  await addEvent(o.id, { note: "paid: Odoo order, e-mail and portal account not connected yet" });
}

async function createOrder(req: Request, b: any) {
  const q = await quote(b, { checkVat: true });
  if (q.buyer === "company" && q.vat && q.vatState === "invalid") throw new Bad("vat_invalid");
  if (q.buyer === "company" && q.vat && q.vatState === "unverified" && q.country !== "BE" && q.eu) throw new Bad("vat_unverified");
  const c = b.customer || {}, cust = { company: str(c.company), first: str(c.first, 80), last: str(c.last, 80), email: str(c.email, 160).toLowerCase(), phone: str(c.phone, 40), street: str(c.street), zip: str(c.zip, 20), city: str(c.city, 80) };
  const missing = (["first", "last", "email", "street", "zip", "city"] as const).filter((k) => !cust[k]);
  if (q.buyer === "company" && !cust.company) missing.push("company" as never);
  if (missing.length) throw new Bad("missing", missing.join(","));
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(cust.email)) throw new Bad("email");
  if (b.terms !== true) throw new Bad("terms");
  const lang = LANGS.includes(b.lang) ? b.lang : "en";
  const origin = req.headers.get("origin") || ""; const site = ORIGINS.includes(origin) ? origin : ORIGINS[0];
  if (MOLLIE && !MOLLIE.startsWith("test_") && !ALLOW_LIVE) throw new Bad("live_key_refused", "A live Mollie key is set but live payments are not switched on.");
  const provider = MOLLIE ? "mollie" : "simulator", test = !(MOLLIE.startsWith("live_") && ALLOW_LIVE);
  const token = hex(20); let number = orderNumber(), row: any = null;
  for (let i = 0; i < 4 && !row; i++) {
    const { data, error } = await db.from("evck_orders").insert({ number, token, status: "open", provider, test, amount: q.total, currency: "EUR", lang, country: q.country, buyer: q.buyer, email: cust.email, customer: cust, items: q.lines, totals: q, pay_choice: str(b.pay, 30) }).select().single();
    if (error) { if (String(error.message).includes("duplicate")) { number = orderNumber(); continue; } throw new Error(error.message); }
    row = data;
  }
  if (!row) throw new Error("could not create order");
  const back = `${site}/${lang}/order-confirmed/?o=${token}`;
  if (provider === "simulator") return { number, token, provider, checkoutUrl: `${site}/${lang}/test-payment/?o=${token}`, total: q.total };
  const body: Record<string, unknown> = { amount: { currency: "EUR", value: q.total.toFixed(2) }, description: `EVChargeking ${number}`, redirectUrl: back, webhookUrl: `${FN_URL}/mollie-webhook`, locale: MLOCALE[lang], metadata: { order: number } };
  const method = PAYMAP[str(b.pay, 30)]; let res = await mollie("/payments", { method: "POST", body: JSON.stringify(method ? { ...body, method } : body) });
  if (!res.ok && method) res = await mollie("/payments", { method: "POST", body: JSON.stringify(body) });   // method not active on the account: let Mollie show its own list
  if (!res.ok) { await setStatus(row, "failed"); await addEvent(row.id, { mollie_error: res.j?.detail || res.status }); throw new Bad("payment_start", res.j?.detail || "Mollie refused the payment"); }
  await db.from("evck_orders").update({ mollie_id: res.j.id }).eq("id", row.id);
  return { number, token, provider, checkoutUrl: res.j?._links?.checkout?.href, total: q.total };
}
const MSTATUS: Record<string, string> = { paid: "paid", authorized: "paid", open: "open", pending: "pending", failed: "failed", canceled: "canceled", expired: "expired" };
async function syncMollie(o: any) {
  if (!o.mollie_id || !MOLLIE) return o.status;
  const res = await mollie("/payments/" + o.mollie_id); if (!res.ok) return o.status;
  const st = MSTATUS[res.j.status] || o.status; await setStatus(o, st, { pay_method: res.j.method || null }); return o.status === "paid" ? "paid" : st;
}
async function statusOf(token: string) {
  const { data: o } = await db.from("evck_orders").select("*").eq("token", token).maybeSingle();
  if (!o) throw new Bad("not_found");
  let status = o.status; if (o.provider === "mollie" && ["open", "pending"].includes(o.status)) status = await syncMollie(o);
  return { number: o.number, status, provider: o.provider, test: o.test, total: Number(o.amount), currency: o.currency, lang: o.lang, country: o.country, lines: (o.items || []).map((l: any) => ({ pid: l.pid, name: l.name, options: l.options, qty: l.qty })), email: String(o.email).replace(/^(.).*(@.*)$/, "$1***$2") };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: cors(req) });
  const url = new URL(req.url), path = url.pathname.replace(/^.*\/evck-shop/, "") || "/";
  try {
    if (req.method === "GET" && path === "/") return json(req, { ok: true, service: "evck-shop", payments: MOLLIE ? (MOLLIE.startsWith("test_") ? "mollie-test" : ALLOW_LIVE ? "mollie-live" : "mollie-live-refused") : "simulator", products: Object.keys((await cat()).products).length });
    if (req.method === "GET" && path === "/status") return json(req, await statusOf(str(url.searchParams.get("o"), 60)));
    if (req.method === "POST" && path === "/mollie-webhook") {
      const id = str(new URLSearchParams(await req.text()).get("id"), 40);
      const { data: o } = await db.from("evck_orders").select("*").eq("mollie_id", id).maybeSingle();
      if (o) await syncMollie(o);
      return new Response("ok", { status: 200 });   // always 200, so Mollie cannot probe which ids exist
    }
    if (req.method !== "POST") return json(req, { error: "not_found" }, 404);
    const b = await req.json().catch(() => ({}));
    if (path === "/quote") return json(req, await quote(b));
    if (path === "/vat-check") {
      const country = str(b.country, 2).toUpperCase(), vat = str(b.vat, 20).replace(/[\s.\-]/g, "").toUpperCase();
      if (!vatFormat(country, vat)) return json(req, { valid: false, reason: "format" });
      return json(req, { valid: await viesValid(country, vat) });
    }
    if (path === "/order") return json(req, await createOrder(req, b));
    if (path === "/simulate") {
      const { data: o } = await db.from("evck_orders").select("*").eq("token", str(b.token, 60)).maybeSingle();
      if (!o) throw new Bad("not_found");
      if (o.provider !== "simulator") throw new Bad("not_simulated");
      const result = ["paid", "failed", "canceled", "expired"].includes(b.result) ? b.result : "failed";
      await setStatus(o, result, { pay_method: "simulator" });
      return json(req, { number: o.number, status: o.status === "paid" ? "paid" : result });
    }
    return json(req, { error: "not_found" }, 404);
  } catch (e) {
    if (e instanceof Bad) return json(req, { error: e.code, detail: e.message !== e.code ? e.message : undefined }, e.code === "not_found" ? 404 : 400);
    console.error(e); return json(req, { error: "server" }, 500);
  }
});
