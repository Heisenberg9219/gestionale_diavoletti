import { useEffect, useState } from "react";
import { PencilLine, Search, Warehouse } from "lucide-react";
import { request } from "../api";
import PaginationControls from "../components/PaginationControls";
import "../products.css";

const list = (data) => data?.results || data || [];

export default function InventoryPage() {
  const [stock, setStock] = useState([]); const [query, setQuery] = useState(""); const [loading, setLoading] = useState(true); const [message, setMessage] = useState("");
  const [page, setPage] = useState(1); const [pageSize, setPageSize] = useState(25); const [total, setTotal] = useState(0);
  const load = (requestedPage = page, requestedPageSize = pageSize) => {
    setLoading(true);
    request(`/inventory/stock/?search=${encodeURIComponent(query)}&page=${requestedPage}&page_size=${requestedPageSize}`)
      .then((data) => { const rows = list(data); setStock(rows); setTotal(data.count ?? rows.length); setPage(requestedPage); })
      .catch(() => setMessage("Non è stato possibile caricare le giacenze."))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(1, 25); }, []);
  async function adjust(item) { const quantity = window.prompt("Nuova quantità fisica:", item.quantity_on_hand); if (quantity === null || quantity === "") return; const next = Number(quantity); if (!Number.isInteger(next) || next < 0) return setMessage("Inserisci una quantità intera maggiore o uguale a zero."); const reason = window.prompt("Motivo della rettifica:", "Verifica magazzino"); if (!reason) return; try { await request("/inventory/movements/adjust/", { method: "POST", body: JSON.stringify({ variant: item.variant, location: item.location, quantity_delta: next - Number(item.quantity_on_hand), reason }) }); setMessage("Rettifica registrata nello storico movimenti."); load(); } catch (error) { setMessage(error.message); } }
  return <section className="products-page"><div className="page-title-row"><div><p className="eyebrow">Prodotti</p><h2>Magazzino</h2><span>Disponibilità reale degli articoli nelle singole sedi.</span></div><div className="page-note"><Warehouse size={17} /> Quantità disponibili</div></div><form className="products-search" onSubmit={(event) => { event.preventDefault(); load(1); }}><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Cerca SKU, articolo o sede" /><button>Ricerca</button></form>{message && <p className="catalog-error">{message}</p>}<article className="products-list"><div className="products-heading stock-heading"><span>Articolo</span><span>Taglia</span><span>Sede</span><span>Disponibilità</span></div>{loading ? <p>Caricamento giacenze...</p> : !stock.length ? <p>Nessuna giacenza trovata.</p> : stock.map((item) => <div className="product-row stock-row" key={item.id}><div><strong>{item.product_name || item.variant}</strong><span>{item.variant_sku || item.sku || ""}</span></div><span>{item.size_label || "—"}</span><span>{item.location_name || item.location}</span><div className="stock-actions"><b className={item.quantity_on_hand === 0 ? "zero-stock" : ""}>{item.quantity_on_hand}</b><button title="Rettifica quantità" onClick={() => adjust(item)}><PencilLine size={16} /></button></div></div>)}</article>{!loading && <PaginationControls page={page} pageSize={pageSize} total={total} onPageChange={(nextPage) => load(nextPage)} onPageSizeChange={(nextPageSize) => load(1, nextPageSize)} />}</section>;
}
