import { useEffect, useRef, useState } from "react";
import { Barcode, Minus, Plus, Search, ShoppingCart } from "lucide-react";
import { request } from "../api";
import "../new-sale.css";

const euro = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
const list = (payload) => payload.results || payload || [];

export default function NewSalePage({ onNavigate }) {
  const [session, setSession] = useState(null);
  const [register, setRegister] = useState(null);
  const [sale, setSale] = useState(null);
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState([]);
  const [labels, setLabels] = useState({});
  const [message, setMessage] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    Promise.all([request("/sales/sessions/"), request("/sales/registers/")]).then(([sessions, registers]) => {
      const open = list(sessions).find((item) => item.status === "OPEN");
      setSession(open || null);
      setRegister(list(registers).find((item) => item.id === open?.cash_register) || null);
    }).catch(() => setMessage("Non è stato possibile verificare la sessione di cassa."));
  }, []);

  async function ensureSale() {
    if (sale) return sale;
    const created = await request("/sales/sales/", { method: "POST", body: JSON.stringify({ location: register.location, cash_session: session.id }) });
    setSale(created);
    return created;
  }

  async function search(event) {
    event?.preventDefault();
    if (!query.trim()) return;
    setMessage("");
    try {
      const found = list(await request(`/catalog/variants/?search=${encodeURIComponent(query.trim())}`));
      setMatches(found);
      if (found.length === 1) await addVariant(found[0]);
    } catch { setMessage("Ricerca articolo non disponibile."); }
  }

  async function addVariant(variant) {
    try {
      const currentSale = await ensureSale();
      const existing = currentSale.lines?.find((line) => line.variant === variant.id);
      const line = await request(`/sales/sales/${currentSale.id}/set-line/`, { method: "POST", body: JSON.stringify({ variant: variant.id, quantity: (existing?.quantity || 0) + 1 }) });
      const refreshed = await request(`/sales/sales/${currentSale.id}/`);
      setSale(refreshed);
      setLabels((current) => ({ ...current, [variant.id]: `${variant.product_name} · ${variant.color_name || ""} ${variant.size_label || ""}`.trim() }));
      setMatches([]); setQuery(""); inputRef.current?.focus();
    } catch (err) { setMessage(err.message); }
  }

  async function changeQuantity(line, delta) {
    if (line.quantity + delta < 1) return;
    try {
      await request(`/sales/sales/${sale.id}/set-line/`, { method: "POST", body: JSON.stringify({ variant: line.variant, quantity: line.quantity + delta }) });
      setSale(await request(`/sales/sales/${sale.id}/`));
    } catch (err) { setMessage(err.message); }
  }

  if (!session || !register) return <section className="new-sale-empty"><Barcode size={28} /><h2>Apri prima la cassa</h2><p>Per iniziare una vendita è necessaria una sessione di cassa aperta.</p><button className="primary-action" onClick={() => onNavigate("Cassa")}>Vai alla cassa</button></section>;
  return <section className="new-sale-page">
    <div className="page-title-row"><div><p className="eyebrow">Cassa · {register.name}</p><h2>Nuova vendita</h2><span>Scansiona un barcode o cerca un articolo.</span></div><div className="sale-draft-badge"><ShoppingCart size={18} />{sale ? "Scontrino in corso" : "Scontrino vuoto"}</div></div>
    <div className="pos-layout"><section className="pos-products"><form className="pos-search" onSubmit={search}><Barcode size={21} /><input ref={inputRef} autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Scansiona barcode o cerca per SKU / nome" /><button aria-label="Cerca"><Search size={19} /></button></form>{message && <p className="pos-message">{message}</p>}{matches.length > 1 && <div className="product-matches">{matches.map((variant) => <button key={variant.id} onClick={() => addVariant(variant)}><div><strong>{variant.product_name}</strong><span>{variant.sku} · {variant.color_name || ""} {variant.size_label || ""}</span></div><b>Seleziona</b></button>)}</div>}<div className="pos-hint"><Barcode size={19} /><span>Con uno scanner USB il codice viene inserito qui automaticamente: premi Invio per aggiungere l’articolo.</span></div></section>
      <aside className="receipt-panel"><div className="receipt-heading"><div><p>Scontrino</p><h3>{sale?.number || "Nuova vendita"}</h3></div><span>{sale?.lines?.length || 0} righe</span></div><div className="receipt-lines">{sale?.lines?.length ? sale.lines.map((line) => <div className="receipt-line" key={line.id}><div><strong>{labels[line.variant] || "Articolo aggiunto"}</strong><span>{euro.format(Number(line.net_amount || 0))}</span></div><div className="quantity-control"><button onClick={() => changeQuantity(line, -1)} aria-label="Diminuisci quantità"><Minus size={15} /></button><b>{line.quantity}</b><button onClick={() => changeQuantity(line, 1)} aria-label="Aumenta quantità"><Plus size={15} /></button></div></div>) : <p className="receipt-empty">Lo scontrino è pronto. Aggiungi il primo articolo.</p>}</div><div className="receipt-total"><span>Totale</span><strong>{euro.format(Number(sale?.final_total_amount || 0))}</strong></div><button className="primary-action receipt-pay" disabled={!sale?.lines?.length}>Vai al pagamento</button></aside></div>
  </section>;
}
