import { Fragment, useEffect, useRef, useState } from "react";
import { ArrowLeftRight, History, Minus, PencilLine, Plus, Search, Warehouse } from "lucide-react";
import { request } from "../api";
import PaginationControls from "../components/PaginationControls";
import { notify } from "../components/Toasts";
import "../products.css";

const list = (data) => data?.results || data || [];
const dateTime = new Intl.DateTimeFormat("it-IT", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const REASONS = [
  "Verifica magazzino",
  "Merce arrivata dal fornitore",
  "Articolo danneggiato",
  "Articolo smarrito",
  "Errore di carico",
];
const LEVELS = [
  ["", "Tutti", "total"],
  ["available", "Disponibili", "available"],
  ["low", "Pochi pezzi", "low"],
  ["zero", "Esauriti", "zero"],
];

function StockLevel({ quantity, lowMax }) {
  const tone = quantity <= 0 ? "zero" : quantity <= lowMax ? "low" : "ok";
  return <b className={`stock-level ${tone}`}>{quantity}</b>;
}

export default function InventoryPage() {
  const [stock, setStock] = useState([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [total, setTotal] = useState(0);
  const [locations, setLocations] = useState([]);
  const [location, setLocation] = useState("");
  const [level, setLevel] = useState("");
  const [summary, setSummary] = useState(null);
  // Riga aperta: { id, mode: "adjust" | "move" | "history" } e i valori del suo pannello.
  const [panel, setPanel] = useState(null);
  const [saving, setSaving] = useState(false);
  const searchRef = useRef(null);

  const load = (requestedPage = page, requestedPageSize = pageSize, filters = {}) => {
    const nextLevel = filters.level ?? level;
    const nextLocation = filters.location ?? location;
    const base = `search=${encodeURIComponent(query)}${nextLocation ? `&location=${nextLocation}` : ""}`;
    setLoading(true);
    request(
      `/inventory/stock/?${base}${nextLevel ? `&level=${nextLevel}` : ""}&page=${requestedPage}&page_size=${requestedPageSize}`,
    )
      .then((data) => {
        const rows = list(data);
        setStock(rows);
        setTotal(data.count ?? rows.length);
        setPage(requestedPage);
        setMessage("");
      })
      .catch(() => setMessage("Non è stato possibile caricare le giacenze."))
      .finally(() => setLoading(false));
    request(`/inventory/stock/summary/?${base}`)
      .then(setSummary)
      .catch(() => setSummary(null));
  };
  useEffect(() => {
    load(1, 25);
    request("/core/locations/")
      .then((data) => setLocations(list(data).filter((item) => item.is_active !== false)))
      .catch(() => setLocations([]));
  }, []);

  const lowMax = summary?.low_stock_max ?? 2;
  const locationName = (id) => locations.find((item) => item.id === id)?.name || "";

  function openPanel(item, mode) {
    if (panel?.id === item.id && panel.mode === mode) return setPanel(null);
    setMessage("");
    if (mode === "adjust")
      setPanel({ id: item.id, mode, quantity: String(item.quantity_on_hand), reason: REASONS[0], note: "" });
    if (mode === "move") {
      const destination = locations.find((entry) => entry.id !== item.location)?.id || "";
      setPanel({ id: item.id, mode, quantity: "1", destination });
    }
    if (mode === "history") {
      setPanel({ id: item.id, mode, movements: null });
      request(
        `/inventory/movements/?variant=${item.variant}&location=${item.location}&ordering=-occurred_at&page_size=10`,
      )
        .then((data) =>
          setPanel((current) => (current?.id === item.id ? { ...current, movements: list(data) } : current)),
        )
        .catch(() =>
          setPanel((current) => (current?.id === item.id ? { ...current, movements: [] } : current)),
        );
    }
  }
  const updatePanel = (key, value) => setPanel((current) => ({ ...current, [key]: value }));

  async function adjust(event, item) {
    event.preventDefault();
    const next = Number(panel.quantity);
    if (panel.quantity === "" || !Number.isInteger(next) || next < 0)
      return setMessage("Inserisci una quantità intera maggiore o uguale a zero.");
    const delta = next - Number(item.quantity_on_hand);
    if (delta === 0) return setPanel(null);
    const reason = [panel.reason, panel.note.trim()].filter(Boolean).join(" · ");
    if (!reason) return;
    setSaving(true);
    try {
      await request("/inventory/movements/adjust/", {
        method: "POST",
        body: JSON.stringify({
          variant: item.variant,
          location: item.location,
          quantity_delta: delta,
          reason,
        }),
      });
      setPanel(null);
      notify(
        `Rettifica registrata nello storico movimenti. ${item.variant_sku}: ${item.quantity_on_hand} → ${next}.`,
      );
      load();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  }

  async function move(event, item) {
    event.preventDefault();
    const quantity = Number(panel.quantity);
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > item.quantity_on_hand)
      return setMessage(`Puoi spostare da 1 a ${item.quantity_on_hand} pezzi.`);
    if (!panel.destination) return setMessage("Scegli la sede di destinazione.");
    setSaving(true);
    try {
      await request(`/inventory/stock/${item.id}/transfer/`, {
        method: "POST",
        body: JSON.stringify({ destination_location: panel.destination, quantity }),
      });
      setPanel(null);
      notify(
        `${quantity} ${quantity === 1 ? "pezzo spostato" : "pezzi spostati"} in ${locationName(panel.destination)}.`,
      );
      load();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  }

  function changeLevel(value) {
    setLevel(value);
    setPanel(null);
    load(1, pageSize, { level: value });
  }
  function changeLocation(value) {
    setLocation(value);
    setPanel(null);
    load(1, pageSize, { location: value });
  }

  return (
    <section className="products-page inventory-page">
      <div className="page-title-row">
        <div>
          <p className="eyebrow">Prodotti</p>
          <h2>Magazzino</h2>
          <span>Disponibilità reale degli articoli nelle singole sedi.</span>
        </div>
        <div className="page-note">
          <Warehouse size={17} /> Quantità disponibili
        </div>
      </div>
      <div className="inventory-toolbar">
        <form
          className="products-search"
          onSubmit={(event) => {
            event.preventDefault();
            setPanel(null);
            load(1);
          }}
        >
          <Search size={18} />
          <input
            ref={searchRef}
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Cerca SKU, articolo o sede"
          />
          <button>Ricerca</button>
        </form>
        {locations.length > 1 && (
          <select
            className="inventory-location"
            aria-label="Sede"
            value={location}
            onChange={(event) => changeLocation(event.target.value)}
          >
            <option value="">Tutte le sedi</option>
            {locations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        )}
        <div className="seg inventory-levels" role="group" aria-label="Filtra per disponibilità">
          {LEVELS.map(([value, label, key]) => (
            <button key={key} type="button" aria-pressed={level === value} onClick={() => changeLevel(value)}>
              {label}
              {summary && <small className={`level-count ${key}`}>{summary[key]}</small>}
            </button>
          ))}
        </div>
      </div>
      {message && <p className="catalog-error">{message}</p>}
      <article className="products-list inventory-list">
        <div className="stockrow stockrow-heading">
          <span>Articolo</span>
          <span>Taglia</span>
          <span>Sede</span>
          <span className="num">Disponibilità</span>
          <span className="num">Azioni</span>
        </div>
        {loading ? (
          <p className="empty-note">Caricamento giacenze...</p>
        ) : !stock.length ? (
          <p className="empty-note">
            {query || level || location
              ? "Nessuna giacenza trovata con questi filtri."
              : "Nessuna giacenza trovata. I pezzi entrano in magazzino dal Catalogo (quantità da caricare), dagli Ordini acquisto o dai Documenti."}
          </p>
        ) : (
          stock.map((item) => {
            const open = panel?.id === item.id ? panel.mode : null;
            const delta =
              open === "adjust" && panel.quantity !== "" ? Number(panel.quantity) - item.quantity_on_hand : 0;
            return (
              <Fragment key={item.id}>
                <div className={`stockrow${open ? " open" : ""}`}>
                  <div>
                    <strong>{item.product_name || item.variant}</strong>
                    <span>{item.variant_sku || item.sku || ""}</span>
                  </div>
                  <span>{item.size_label || "—"}</span>
                  <span>{item.location_name || item.location}</span>
                  <span className="num">
                    <StockLevel quantity={item.quantity_on_hand} lowMax={lowMax} />
                  </span>
                  <span className="stockrow-actions">
                    <button
                      type="button"
                      title="Rettifica quantità"
                      aria-pressed={open === "adjust"}
                      onClick={() => openPanel(item, "adjust")}
                    >
                      <PencilLine size={15} /> Rettifica
                    </button>
                    {locations.length > 1 && (
                      <button
                        type="button"
                        title="Sposta in un'altra sede"
                        aria-pressed={open === "move"}
                        disabled={item.quantity_on_hand <= 0}
                        onClick={() => openPanel(item, "move")}
                      >
                        <ArrowLeftRight size={15} /> Sposta
                      </button>
                    )}
                    <button
                      type="button"
                      title="Ultimi movimenti"
                      aria-label="Ultimi movimenti"
                      aria-pressed={open === "history"}
                      onClick={() => openPanel(item, "history")}
                    >
                      <History size={15} />
                    </button>
                  </span>
                </div>
                {open === "adjust" && (
                  <form className="inventory-panel" onSubmit={(event) => adjust(event, item)}>
                    <label>
                      Nuova quantità fisica:
                      <span className="stepper">
                        <button
                          type="button"
                          aria-label="Un pezzo in meno"
                          onClick={() =>
                            updatePanel("quantity", String(Math.max(0, Number(panel.quantity || 0) - 1)))
                          }
                        >
                          <Minus size={15} />
                        </button>
                        <input
                          autoFocus
                          inputMode="numeric"
                          value={panel.quantity}
                          onChange={(event) =>
                            updatePanel("quantity", event.target.value.replace(/[^0-9]/g, ""))
                          }
                        />
                        <button
                          type="button"
                          aria-label="Un pezzo in più"
                          onClick={() => updatePanel("quantity", String(Number(panel.quantity || 0) + 1))}
                        >
                          <Plus size={15} />
                        </button>
                      </span>
                      <small className={delta > 0 ? "plus" : delta < 0 ? "minus" : ""}>
                        {delta === 0
                          ? `Ora: ${item.quantity_on_hand}`
                          : `${delta > 0 ? "+" : ""}${delta} rispetto a ${item.quantity_on_hand}`}
                      </small>
                    </label>
                    <label>
                      Motivo della rettifica:
                      <select
                        value={panel.reason}
                        onChange={(event) => updatePanel("reason", event.target.value)}
                      >
                        {REASONS.map((reason) => (
                          <option key={reason}>{reason}</option>
                        ))}
                      </select>
                    </label>
                    <label className="grow">
                      Nota
                      <input
                        value={panel.note}
                        placeholder="Facoltativa, es. numero bolla"
                        onChange={(event) => updatePanel("note", event.target.value)}
                      />
                    </label>
                    <div className="inventory-panel-actions">
                      <button type="button" className="secondary-action" onClick={() => setPanel(null)}>
                        Annulla
                      </button>
                      <button className="primary-action" disabled={saving || delta === 0}>
                        {saving ? "Salvataggio..." : "Salva rettifica"}
                      </button>
                    </div>
                  </form>
                )}
                {open === "move" && (
                  <form className="inventory-panel" onSubmit={(event) => move(event, item)}>
                    <label>
                      Pezzi da spostare
                      <input
                        autoFocus
                        inputMode="numeric"
                        value={panel.quantity}
                        onChange={(event) =>
                          updatePanel("quantity", event.target.value.replace(/[^0-9]/g, ""))
                        }
                      />
                      <small>Disponibili: {item.quantity_on_hand}</small>
                    </label>
                    <label>
                      Da {item.location_name} a
                      <select
                        value={panel.destination}
                        onChange={(event) => updatePanel("destination", event.target.value)}
                      >
                        {locations
                          .filter((entry) => entry.id !== item.location)
                          .map((entry) => (
                            <option key={entry.id} value={entry.id}>
                              {entry.name}
                            </option>
                          ))}
                      </select>
                    </label>
                    <div className="inventory-panel-actions">
                      <button type="button" className="secondary-action" onClick={() => setPanel(null)}>
                        Annulla
                      </button>
                      <button className="primary-action" disabled={saving}>
                        {saving ? "Spostamento..." : "Sposta"}
                      </button>
                    </div>
                  </form>
                )}
                {open === "history" && (
                  <div className="inventory-panel history">
                    {panel.movements === null ? (
                      <p className="empty-note">Caricamento movimenti...</p>
                    ) : !panel.movements.length ? (
                      <p className="empty-note">Nessun movimento registrato per questa sede.</p>
                    ) : (
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Quando</th>
                            <th>Movimento</th>
                            <th>Nota</th>
                            <th className="num">Pezzi</th>
                          </tr>
                        </thead>
                        <tbody>
                          {panel.movements.map((movement) => (
                            <tr key={movement.id}>
                              <td className="tabular">{dateTime.format(new Date(movement.occurred_at))}</td>
                              <td>{movement.movement_type_label || movement.movement_type}</td>
                              <td>{movement.notes || movement.reference_number || "—"}</td>
                              <td className={`num ${movement.quantity_delta > 0 ? "plus" : "minus"}`}>
                                {movement.quantity_delta > 0 ? "+" : ""}
                                {movement.quantity_delta}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </Fragment>
            );
          })
        )}
      </article>
      {!loading && stock.length > 0 && (
        <PaginationControls
          page={page}
          pageSize={pageSize}
          total={total}
          onPageChange={(nextPage) => load(nextPage)}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(nextPageSize);
            load(1, nextPageSize);
          }}
        />
      )}
    </section>
  );
}
