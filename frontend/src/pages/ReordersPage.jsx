import { useEffect, useState } from "react";
import { ClipboardList, Plus, Search, Trash2 } from "lucide-react";
import { request } from "../api";
import "../products.css";

const list = (data) => data?.results || data || [];

export default function ReordersPage() {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [stockMatches, setStockMatches] = useState([]);
  const [adding, setAdding] = useState(false);
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);

  const load = () => request(`/reorders/items/?status=PENDING&search=${encodeURIComponent(query)}`)
    .then((data) => setItems(list(data)))
    .catch(() => setMessage("Impossibile caricare i riordini."));

  useEffect(() => { load(); }, []);

  async function updateQuantity(item, value) {
    const requestedQuantity = Number(value);
    if (!Number.isInteger(requestedQuantity) || requestedQuantity < 1) return;
    try {
      await request(`/reorders/items/${item.id}/update-pending/`, {
        method: "POST",
        body: JSON.stringify({ requested_quantity: requestedQuantity, notes: item.notes || "" }),
      });
      load();
    } catch (error) {
      setMessage(error.message);
    }
  }
  async function searchStock(value) {
    setQuery(value);
    if (value.trim().length < 2) return setStockMatches([]);
    try { setStockMatches(list(await request(`/inventory/stock/?search=${encodeURIComponent(value)}`))); }
    catch (error) { setMessage(error.message); }
  }
  async function addFromStock(item) {
    try { await request("/reorders/items/", { method: "POST", body: JSON.stringify({ variant: item.variant, location: item.location, requested_quantity: 1, reason: "Inserimento manuale", notifications_enabled: notificationsEnabled }) }); if (notificationsEnabled) await request("/reorders/items/refresh-notifications/", { method: "POST", body: JSON.stringify({}) }); setAdding(false); setNotificationsEnabled(false); setStockMatches([]); setQuery(""); load(); }
    catch (error) { setMessage(error.message); }
  }
  async function removeItem(item) {
    const reason = window.prompt("Motivo della rimozione:", "Non necessario");
    if (!reason) return;
    try { await request(`/reorders/items/${item.id}/remove/`, { method: "POST", body: JSON.stringify({ reason }) }); load(); }
    catch (error) { setMessage(error.message); }
  }

  return <section className="products-page">
    <div className="page-title-row"><div><p className="eyebrow">Prodotti</p><h2>Riordini</h2><span>Articoli da rifornire prima di creare un ordine fornitore.</span></div><button className="primary-action" onClick={() => { setNotificationsEnabled(false); setAdding(true); }}><Plus size={17} /> Aggiungi articolo</button></div>
    {adding ? <div className="reorder-add-panel"><label className="products-search"><Search size={18} /><input autoFocus value={query} onChange={(event) => searchStock(event.target.value)} placeholder="Cerca nel magazzino per articolo o SKU" /></label><div className="reorder-notification-option"><div><strong>Notifica riordino</strong><span>Ricevi un avviso per l’articolo che aggiungerai.</span></div><label className="notification-control"><input type="checkbox" checked={notificationsEnabled} onChange={(event) => setNotificationsEnabled(event.target.checked)} /><span>Avvisami</span></label></div><p className="reorder-search-hint">Digita almeno due caratteri per cercare una variante presente in Magazzino.</p>{stockMatches.map((item) => <div className="reorder-stock-match" key={item.id}><div><strong>{item.product_name || item.variant}</strong><span>{item.sku} · {item.location_name || item.location}</span></div><button type="button" onClick={() => addFromStock(item)}><Plus size={16} /> Aggiungi</button></div>)}</div> : <form className="products-search" onSubmit={(event) => { event.preventDefault(); load(); }}><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Cerca articolo o SKU" /><button>Ricerca</button></form>}
    {message && <p className="catalog-error">{message}</p>}
    <article className="products-list"><div className="products-heading"><span>Articolo</span><span>Sede</span><span>Quantità</span></div>{!items.length ? <div className="empty-product-state"><ClipboardList size={28} /><strong>Nessun riordino pendente</strong><span>Gli articoli da rifornire compariranno qui.</span></div> : items.map((item) => <div className="product-row" key={item.id}><div><strong>{item.variant}</strong><span>{item.reason || "Inserito in lista"}</span></div><span>{item.location}</span><div className="reorder-line-actions"><input className="reorder-quantity" type="number" min="1" defaultValue={item.requested_quantity} onBlur={(event) => updateQuantity(item, event.target.value)} /><button onClick={() => removeItem(item)} title="Rimuovi dalla lista"><Trash2 size={16} /></button></div></div>)}</article>
  </section>;
}
