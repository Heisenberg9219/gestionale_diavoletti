import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import { request } from "../api";

// Ricerca globale (Ctrl K): pagine, articoli con giacenza, clienti, scontrini e buoni.
// Da ogni risultato si fa subito l'azione: vendere, fare un reso, aprire la pagina.

const euro = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
const asList = (payload) => payload?.results || payload || [];
const dateFormat = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short" });

function stockChip(quantity) {
  if (quantity == null) return null;
  const tone = quantity <= 0 ? "zero" : quantity <= 2 ? "low" : "";
  return (
    <span className={`stock-chip ${tone}`}>
      {quantity <= 0 ? "esaurito" : `${quantity} ${quantity === 1 ? "pezzo" : "pezzi"}`}
    </span>
  );
}

export default function CommandPalette({ open, onClose, pages, canOpen, onNavigate, onSell, onReturn }) {
  const [query, setQuery] = useState("");
  const [remote, setRemote] = useState({ variants: [], customers: [], sales: [], vouchers: [] });
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef(null);
  const requestId = useRef(0);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setRemote({ variants: [], customers: [], sales: [], vouchers: [] });
    setActiveIndex(0);
    window.setTimeout(() => inputRef.current?.focus(), 20);
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const text = query.trim();
    if (text.length < 2) {
      setRemote({ variants: [], customers: [], sales: [], vouchers: [] });
      setLoading(false);
      return undefined;
    }
    const id = ++requestId.current;
    setLoading(true);
    const q = encodeURIComponent(text);
    // Ogni fonte è facoltativa: un commesso senza permessi su una pagina non blocca le altre.
    const get = (path, allowed) =>
      allowed
        ? request(path)
            .then(asList)
            .catch(() => [])
        : Promise.resolve([]);
    const timer = window.setTimeout(async () => {
      const [variants, customers, sales, vouchers] = await Promise.all([
        get(
          `/catalog/variants/?search=${q}&active=true&stock_scope=all&page_size=6`,
          canOpen("Catalogo") || canOpen("Nuova vendita"),
        ),
        get(`/customers/customers/?search=${q}&page_size=4`, canOpen("Clienti")),
        get(`/sales/sales/?search=${q}&page_size=4`, canOpen("Storico vendite")),
        get(`/vouchers/vouchers/?search=${q}&page_size=4`, canOpen("Buoni")),
      ]);
      if (id !== requestId.current) return;
      setRemote({ variants, customers, sales, vouchers });
      setLoading(false);
      setActiveIndex(0);
    }, 220);
    return () => window.clearTimeout(timer);
  }, [query, open, canOpen]);

  const rows = useMemo(() => {
    const text = query.trim().toLowerCase();
    const list = [];
    const pageMatches = pages
      .filter((page) => !text || page.label.toLowerCase().includes(text))
      .slice(0, text ? 5 : 8);
    pageMatches.forEach((page) =>
      list.push({
        group: "Pagine",
        key: `page-${page.label}`,
        title: page.label,
        detail: page.group,
        actions: [{ label: "Apri", run: () => onNavigate(page.label) }],
      }),
    );
    remote.variants.forEach((variant) =>
      list.push({
        group: "Articoli",
        key: `variant-${variant.id}`,
        title: variant.product_name || variant.sku,
        detail: [variant.sku, variant.size_label && `taglia ${variant.size_label}`, variant.color_name]
          .filter(Boolean)
          .join(" · "),
        badge: stockChip(variant.stock_quantity),
        actions: [
          canOpen("Nuova vendita") && { label: "Vendi", run: () => onSell(variant.sku) },
          canOpen("Catalogo") && { label: "Catalogo", run: () => onNavigate("Catalogo") },
        ].filter(Boolean),
      }),
    );
    remote.sales.forEach((sale) =>
      list.push({
        group: "Scontrini",
        key: `sale-${sale.id}`,
        title: sale.number || "Vendita in corso",
        detail: `${sale.customer_name || "Vendita banco"} · ${euro.format(Number(sale.final_total_amount || 0))}${
          sale.confirmed_at ? ` · ${dateFormat.format(new Date(sale.confirmed_at))}` : ""
        }`,
        actions: [
          sale.status === "CONFIRMED" && canOpen("Resi") && { label: "Fai reso", run: () => onReturn(sale) },
          { label: "Storico", run: () => onNavigate("Storico vendite") },
        ].filter(Boolean),
      }),
    );
    remote.customers.forEach((customer) =>
      list.push({
        group: "Clienti",
        key: `customer-${customer.id}`,
        title: `${customer.first_name || ""} ${customer.last_name || ""}`.trim() || customer.customer_code,
        detail: [customer.customer_code, customer.phone, customer.email].filter(Boolean).join(" · "),
        actions: [{ label: "Apri clienti", run: () => onNavigate("Clienti") }],
      }),
    );
    remote.vouchers.forEach((voucher) =>
      list.push({
        group: "Buoni",
        key: `voucher-${voucher.id}`,
        title: voucher.code,
        detail: `Saldo ${euro.format(Number(voucher.current_balance || 0))} · ${
          voucher.status === "ACTIVE" ? "attivo" : voucher.status === "EXHAUSTED" ? "esaurito" : "annullato"
        }`,
        actions: [{ label: "Apri buoni", run: () => onNavigate("Buoni") }],
      }),
    );
    return list;
  }, [query, pages, remote, canOpen, onNavigate, onSell, onReturn]);

  if (!open) return null;

  function run(row, actionIndex = 0) {
    const action = row?.actions[actionIndex];
    if (!action) return;
    onClose();
    action.run();
  }

  function onKeyDown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => Math.min(rows.length - 1, index + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(0, index - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      run(rows[activeIndex], event.shiftKey ? 1 : 0);
    }
  }

  let lastGroup = "";
  return (
    <div
      className="palette-layer"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="palette" role="dialog" aria-modal="true" aria-label="Cerca nel gestionale">
        <label className="palette-input">
          <Search size={20} aria-hidden="true" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Cerca articolo, cliente, scontrino, buono o pagina…"
            aria-label="Cerca nel gestionale"
            autoComplete="off"
          />
          <kbd>Esc</kbd>
        </label>
        <div className="palette-results">
          {rows.map((row, index) => {
            const header = row.group !== lastGroup ? row.group : null;
            lastGroup = row.group;
            return (
              <div key={row.key} style={{ display: "contents" }}>
                {header && <div className="palette-group">{header}</div>}
                <div
                  className={`palette-row${index === activeIndex ? " active" : ""}`}
                  onMouseEnter={() => setActiveIndex(index)}
                >
                  <button type="button" className="palette-main" onClick={() => run(row)}>
                    <b>
                      {row.title} {row.badge}
                    </b>
                    <small>{row.detail}</small>
                  </button>
                  <span className="actions">
                    {row.actions.map((action, actionIndex) => (
                      <button
                        key={action.label}
                        type="button"
                        tabIndex={-1}
                        onClick={() => run(row, actionIndex)}
                      >
                        {action.label}
                      </button>
                    ))}
                  </span>
                </div>
              </div>
            );
          })}
          {query.trim().length >= 2 && !loading && rows.length === 0 && (
            <p className="palette-empty">
              Nessun risultato per “{query}”. Prova con lo SKU, il barcode o il cognome.
            </p>
          )}
          {loading && <p className="palette-empty">Ricerca in corso…</p>}
        </div>
        <div className="palette-foot">
          <span>
            <kbd>↑</kbd> <kbd>↓</kbd> scegli
          </span>
          <span>
            <kbd>Invio</kbd> prima azione
          </span>
          <span>
            <kbd>Maiusc</kbd>+<kbd>Invio</kbd> seconda azione
          </span>
        </div>
      </div>
    </div>
  );
}
