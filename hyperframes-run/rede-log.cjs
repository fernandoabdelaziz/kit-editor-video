// Instrumentação de verificação: registra toda tentativa de conexão/DNS/fetch do processo Node do HyperFrames
// (e dos filhos Node, que herdam NODE_OPTIONS). Não altera o comportamento.
const fs = require("fs"), net = require("net"), dns = require("dns");
const LOG = process.env.HF_REDE_LOG || "/tmp/hf_rede.log";
const w = (m) => { try { fs.appendFileSync(LOG, `${new Date().toISOString()} pid=${process.pid} ${m}\n`); } catch {} };
const oc = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...a) {
  let o = Array.isArray(a[0]) ? a[0][0] : a[0];
  const alvo = o && typeof o === "object" ? (o.path ? `unix:${o.path}` : `${o.host || "localhost"}:${o.port}`) : String(a[0]);
  w(`connect ${alvo}`);
  this.once("error", (e) => w(`connect-erro ${alvo} ${e.code || e.message}`));
  return oc.apply(this, a);
};
const ol = dns.lookup; dns.lookup = function (h, ...r) { w(`dns.lookup ${h}`); return ol.call(this, h, ...r); };
if (globalThis.fetch) { const of = globalThis.fetch; globalThis.fetch = function (u, ...r) { w(`fetch ${typeof u === "string" ? u : (u && (u.url || u.href)) || u}`); return of.call(this, u, ...r); }; }
