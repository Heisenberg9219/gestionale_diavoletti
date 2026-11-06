import { useEffect, useState } from "react";
import { ClipboardList, Copy, PackageCheck, Plus, Search, Trash2 } from "lucide-react";
import { request } from "../api";
import { askText } from "../components/Dialogs";
import { notify } from "../components/Toasts";
import "../products.css";

const list = (data) => data?.results || data || [];
const ARRIVED_REASON = "Merce arrivata dal fornitore";

function StockChip({ quantity }) {
  if (quantity == null) return null;
  const tone = quantity <= 0 ? "zero" : quantity <= 2 ? "low" : "ok";
  return (
    <span className={`stock-level ${tone}`} title="Giacenza attuale nella sede">
      {quantity}
    </span>
  );
}
const variantText = (item) =>
  [item.variant_sku || item.sku, item.size_label && `tg ${item.size_label}`, item.color_name]
    .filter(Boolean)
    .join(" · ");

export default function ReordersPage() {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [stockMatches, setStockMatches] = useState([]);
  const [adding, setAdding] = useState(false);
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [suggested, setSuggested] = useState([]);
  const [arrival, setArrival] = useState(null); // { id, quantity }
  const [busy, setBusy] = useState(false);

  const load = () =>
    request(`/reorders/items/?status=PENDING&search=${encodeURIComponent(query)}&page_size=200`)
      .then((data) => setItems(list(data)))
      .catch(() => setMessage("Impossibile caricare i riordini."));

  // Articoli esauriti o con pochi pezzi in magazzino, non ancora in lista.
  const loadSuggested = () =>
    Promise.all([
      request("/inventory/stock/?level=zero&page_size=50").then(list),
      request("/inventory/stock/?level=low&page_size=50").then(list),
    ])
      .then(([zero, low]) => setSuggested([...zero, ...low]))
      .catch(() => setSuggested([]));

  useEffect(() => {
    load();
    loadSuggested();
  }, []);

  const pendingKeys = new Set(items.map((item) => `${item.variant}:${item.location}`));
  const suggestions = suggested.filter((item) => !pendingKeys.has(`${item.variant}:${item.location}`));
  const groups = [];
  items.forEach((item) => {
    const key = item.supplier || "";
    let group = groups.find((entry) => entry.key === key);
    if (!group) {
      group = { key, name: item.supplier_name || "Senza fornitore", items: [] };
      groups.push(group);
    }
    group.items.push(item);
  });
  groups.sort((a, b) => (a.key === "") - (b.key === "") || a.name.localeCompare(b.name, "it"));

  async function updateQuantity(item, value) {
    const requestedQuantity = Number(value);
    if (!Number.isInteger(requestedQuantity) || requestedQuantity < 1) return;
    if (requestedQuantity === item.requested_quantity) return;
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
    try {
      setStockMatches(list(await request(`/inventory/stock/?search=${encodeURIComponent(value)}`)));
    } catch (error) {
      setMessage(error.message);
    }
  }
  async function addItem(item, { quiet = false, reason = "Inserimento manuale" } = {}) {
    await request("/reorders/items/add/", {
      method: "POST",
      body: JSON.stringify({
        variant: item.variant,
        location: item.location,
        requested_quantity: 1,
        reason,
        notifications_enabled: notificationsEnabled,
      }),
    });
    if (!quiet) notify(`${item.product_name || "Articolo"} aggiunto ai riordini.`);
  }
  async function addFromStock(item) {
    try {
      await addItem(item);
      if (notificationsEnabled)
        await request("/reorders/items/refresh-notifications/", { method: "POST", body: JSON.stringify({}) });
      setAdding(false);
      setNotificationsEnabled(false);
      setStockMatches([]);
      setQuery("");
      load();
    } catch (error) {
      setMessage(error.message);
    }
  }
  async function addSuggested(rows) {
    setBusy(true);
    try {
      for (const row of rows)
        await addItem(row, {
          quiet: rows.length > 1,
          reason: row.quantity_on_hand <= 0 ? "Articolo esaurito" : "Pochi pezzi",
        });
      if (rows.length > 1) notify(`${rows.length} articoli aggiunti ai riordini.`);
      load();
    } catch (error) {
      setMessage(error.message);
      load();
    } finally {
      setBusy(false);
    }
  }
  async function removeItem(item) {
    const reason = await askText("Motivo della rimozione:", "Non necessario");
    if (!reason) return;
    try {
      await request(`/reorders/items/${item.id}/remove/`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      load();
    } catch (error) {
      setMessage(error.message);
    }
  }
  // Merce arrivata (anche se ordinata sul sito del fornitore): carica i pezzi e toglie la riga dalla lista.
  async function confirmArrival(event, item) {
    event.preventDefault();
    const quantity = Number(arrival.quantity);
    if (!Number.isInteger(quantity) || quantity < 1) return setMessage("Indica quanti pezzi sono arrivati.");
    setBusy(true);
    try {
      await request("/inventory/movements/adjust/", {
        method: "POST",
        body: JSON.stringify({
          variant: item.variant,
          location: item.location,
          quantity_delta: quantity,
          reason: ARRIVED_REASON,
        }),
      });
      await request(`/reorders/items/${item.id}/remove/`, {
        method: "POST",
        body: JSON.stringify({ reason: "Arrivato dal fornitore" }),
      });
      setArrival(null);
      notify(
        `${quantity} ${quantity === 1 ? "pezzo caricato" : "pezzi caricati"} in magazzino: ${item.product_name}.`,
      );
      load();
      loadSuggested();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }
  async function copyGroup(group) {
    const text = [
      group.name,
      ...group.items.map(
        (item) => `${item.requested_quantity} × ${item.product_name} · ${variantText(item)}`,
      ),
    ].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      notify("Elenco copiato: incollalo nell'ordine o nell'email al fornitore.");
    } catch {
      setMessage("Non è stato possibile copiare l'elenco negli appunti.");
    }
  }

  return (
    <section className="products-page reorders-page">
      <div className="page-title-row">
        <div>
          <p className="eyebrow">Prodotti</p>
          <h2>Riordini</h2>
          <span>Articoli da rifornire prima di creare un ordine fornitore.</span>
        </div>
        <button
          className="primary-action"
          onClick={() => {
            setNotificationsEnabled(false);
            setAdding(true);
          }}
        >
          <Plus size={17} /> Aggiungi articolo
        </button>
      </div>
      {adding ? (
        <div className="reorder-add-panel">
          <label className="products-search">
            <Search size={18} />
            <input
              autoFocus
              value={query}
              onChange={(event) => searchStock(event.target.value)}
              placeholder="Cerca nel magazzino per articolo o SKU"
            />
          </label>
          <div className="reorder-notification-option">
            <div>
              <strong>Notifica riordino</strong>
              <span>Ricevi un avviso per l’articolo che aggiungerai.</span>
            </div>
            <label className="notification-control">
              <input
                type="checkbox"
                checked={notificationsEnabled}
                onChange={(event) => setNotificationsEnabled(event.target.checked)}
              />
              <span>Avvisami</span>
            </label>
          </div>
          <p className="reorder-search-hint">
            Digita almeno due caratteri per cercare una variante presente in Magazzino.
          </p>
          {stockMatches.map((item) => (
            <div className="reorder-stock-match" key={item.id}>
              <div>
                <strong>{item.product_name || item.variant}</strong>
                <span>
                  {[item.variant_sku || item.sku, item.size_label && `tg ${item.size_label}`]
                    .filter(Boolean)
                    .join(" · ")}{" "}
                  · {item.location_name || item.location}
                </span>
              </div>
              <StockChip quantity={item.quantity_on_hand} />
              <button type="button" onClick={() => addFromStock(item)}>
                <Plus size={16} /> Aggiungi
              </button>
            </div>
          ))}
        </div>
      ) : (
        <form
          className="products-search"
          onSubmit={(event) => {
            event.preventDefault();
            load();
          }}
        >
          <Search size={18} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Cerca articolo o SKU"
          />
          <button>Ricerca</button>
        </form>
      )}
      {message && <p className="catalog-error">{message}</p>}

      {suggestions.length > 0 && (
        <section className="reorder-suggestions" aria-label="Suggeriti dal magazzino">
          <div className="reorder-suggestions-head">
            <div>
              <strong>Suggeriti dal Magazzino</strong>
              <span>
                {suggestions.filter((item) => item.quantity_on_hand <= 0).length} esauriti e{" "}
                {suggestions.filter((item) => item.quantity_on_hand > 0).length} con pochi pezzi, non ancora
                in lista.
              </span>
            </div>
            {suggestions.some((item) => item.quantity_on_hand <= 0) && (
              <button
                type="button"
                className="secondary-action"
                disabled={busy}
                onClick={() => addSuggested(suggestions.filter((item) => item.quantity_on_hand <= 0))}
              >
                Aggiungi tutti gli esauriti
              </button>
            )}
          </div>
          <div className="reorder-suggestion-list">
            {suggestions.slice(0, 12).map((item) => (
              <div className="reorder-suggestion" key={item.id}>
                <StockChip quantity={item.quantity_on_hand} />
                <div>
                  <b>{item.product_name}</b>
                  <span>
                    {[item.variant_sku, item.size_label && `tg ${item.size_label}`, item.location_name]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </div>
                <button type="button" disabled={busy} onClick={() => addSuggested([item])}>
                  <Plus size={15} /> Aggiungi
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {!items.length ? (
        <article className="products-list">
          <div className="empty-product-state">
            <ClipboardList size={28} />
            <strong>Nessun riordino pendente</strong>
            <span>Gli articoli da rifornire compariranno qui.</span>
          </div>
        </article>
      ) : (
        groups.map((group) => (
          <article className="products-list reorder-group" key={group.key || "none"}>
            <header className="reorder-group-head">
              <div>
                <strong>{group.name}</strong>
                <span>
                  {group.items.length} {group.items.length === 1 ? "articolo" : "articoli"} ·{" "}
                  {group.items.reduce((sum, item) => sum + Number(item.requested_quantity || 0), 0)} pezzi
                </span>
              </div>
              <button type="button" className="secondary-action" onClick={() => copyGroup(group)}>
                <Copy size={15} /> Copia elenco
              </button>
            </header>
            <div className="reorder-row reorder-heading">
              <span>Articolo</span>
              <span>Sede</span>
              <span className="num">Giacenza</span>
              <span className="num">Quantità</span>
              <span />
            </div>
            {group.items.map((item) => (
              <div key={item.id}>
                <div className={`reorder-row${arrival?.id === item.id ? " open" : ""}`}>
                  <div>
                    <strong>{item.product_name || item.variant}</strong>
                    <span>
                      {variantText(item)}
                      {item.reason ? ` · ${item.reason}` : ""}
                    </span>
                  </div>
                  <span>{item.location_name || item.location}</span>
                  <span className="num">
                    <StockChip quantity={item.stock_quantity} />
                  </span>
                  <span className="num">
                    <input
                      className="reorder-quantity"
                      type="number"
                      min="1"
                      aria-label={`Quantità da riordinare per ${item.product_name}`}
                      defaultValue={item.requested_quantity}
                      key={`${item.id}-${item.requested_quantity}`}
                      onBlur={(event) => updateQuantity(item, event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") event.currentTarget.blur();
                      }}
                    />
                  </span>
                  <div className="reorder-line-actions">
                    <button
                      type="button"
                      className="reorder-arrived"
                      title="La merce è arrivata: carica i pezzi in magazzino"
                      aria-pressed={arrival?.id === item.id}
                      onClick={() =>
                        setArrival(
                          arrival?.id === item.id
                            ? null
                            : { id: item.id, quantity: String(item.requested_quantity) },
                        )
                      }
                    >
                      <PackageCheck size={15} /> Arrivato
                    </button>
                    <button type="button" onClick={() => removeItem(item)} title="Rimuovi dalla lista">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
                {arrival?.id === item.id && (
                  <form className="inventory-panel" onSubmit={(event) => confirmArrival(event, item)}>
                    <label>
                      <span className="panel-label">
                        Pezzi arrivati <small>vengono caricati in {item.location_name}</small>
                      </span>
                      <input
                        autoFocus
                        inputMode="numeric"
                        value={arrival.quantity}
                        onChange={(event) =>
                          setArrival({ ...arrival, quantity: event.target.value.replace(/[^0-9]/g, "") })
                        }
                      />
                    </label>
                    <span className="reorder-arrival-note">
                      Il carico viene registrato come “{ARRIVED_REASON}” e l’articolo esce dalla lista.
                    </span>
                    <div className="inventory-panel-actions">
                      <button type="button" className="secondary-action" onClick={() => setArrival(null)}>
                        Annulla
                      </button>
                      <button className="primary-action" disabled={busy}>
                        {busy ? "Caricamento..." : "Carica in magazzino"}
                      </button>
                    </div>
                  </form>
                )}
              </div>
            ))}
          </article>
        ))
      )}
    </section>
  );
}
