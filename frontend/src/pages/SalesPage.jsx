import { useEffect, useMemo, useState } from "react";
import { CalendarDays, ChevronDown, Download, Filter, RotateCcw, Search, ShoppingBag, X } from "lucide-react";
import { downloadFile, request } from "../api";
import PaginatedRows from "../components/PaginatedRows";
import "../sales.css";

const euro = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
const dateFormatter = new Intl.DateTimeFormat("it-IT", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const initialFilters = {
  search: "",
  status: "ALL",
  dateFrom: "",
  dateTo: "",
  brand: "",
  category: "",
  season: "",
  location: "",
  cashRegister: "",
  channel: "",
  paymentMethod: "",
};

function listItems(payload) {
  return payload?.results || payload || [];
}
function asInputDate(date) {
  return date.toLocaleDateString("en-CA");
}
function periodRange(preset) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const startOfWeek = new Date(today);
  startOfWeek.setDate(today.getDate() - ((today.getDay() + 6) % 7));
  if (preset === "TODAY") return [today, today];
  if (preset === "YESTERDAY") {
    const day = new Date(today);
    day.setDate(day.getDate() - 1);
    return [day, day];
  }
  if (preset === "LAST_7") {
    const start = new Date(today);
    start.setDate(start.getDate() - 6);
    return [start, today];
  }
  if (preset === "CURRENT_WEEK") return [startOfWeek, today];
  if (preset === "PREVIOUS_WEEK") {
    const end = new Date(startOfWeek);
    end.setDate(end.getDate() - 1);
    const start = new Date(end);
    start.setDate(start.getDate() - 6);
    return [start, end];
  }
  if (preset === "CURRENT_MONTH") return [new Date(today.getFullYear(), today.getMonth(), 1), today];
  return [
    new Date(today.getFullYear(), today.getMonth() - 1, 1),
    new Date(today.getFullYear(), today.getMonth(), 0),
  ];
}
const METHOD_LABELS = {
  CASH: "Contanti",
  CARD: "Carta",
  GIFT_CARD: "Gift card",
  STORE_CREDIT: "Buono reso",
  OTHER: "Altro",
};
const QUICK_PERIODS = [
  ["TODAY", "Oggi"],
  ["YESTERDAY", "Ieri"],
  ["LAST_7", "Ultimi 7 giorni"],
  ["CURRENT_MONTH", "Questo mese"],
];
const statusLabel = (status) =>
  status === "CONFIRMED" ? "Conclusa" : status === "CANCELLED" ? "Annullata" : "Aperta";
const methodsOf = (sale) =>
  [...new Set((sale.payments || []).map((payment) => METHOD_LABELS[payment.method] || payment.method))].join(
    " + ",
  );
const piecesOf = (sale) => (sale.lines || []).reduce((sum, line) => sum + Number(line.quantity || 0), 0);

function SelectField({ label, value, onChange, options }) {
  return (
    <label className="history-filter-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Tutti</option>
        {options.map((option) => (
          <option key={option.id || option.value} value={option.id || option.value}>
            {option.name || option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function SalesPage({ onStartReturn }) {
  const [filters, setFilters] = useState(initialFilters);
  const [sales, setSales] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [periodOpen, setPeriodOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [periodDraft, setPeriodDraft] = useState({ dateFrom: "", dateTo: "", preset: "" });
  const [selectedId, setSelectedId] = useState(null);
  const [options, setOptions] = useState({
    brands: [],
    categories: [],
    seasons: [],
    locations: [],
    registers: [],
  });
  const query = useMemo(() => {
    const params = new URLSearchParams({ ordering: "-opened_at" });
    const fields = {
      search: "search",
      status: "status",
      dateFrom: "date_from",
      dateTo: "date_to",
      brand: "brand",
      category: "category",
      season: "season",
      location: "location",
      cashRegister: "cash_register",
      channel: "channel",
      paymentMethod: "payment_method",
    };
    Object.entries(fields).forEach(([key, parameter]) => {
      if (filters[key] && filters[key] !== "ALL") params.set(parameter, filters[key]);
    });
    return params.toString();
  }, [filters]);
  useEffect(() => {
    setLoading(true);
    setError("");
    request(`/sales/sales/?${query}&page_size=200`)
      .then((payload) => {
        const rows = listItems(payload);
        setSales(rows);
        setSelectedId((current) => (rows.some((sale) => sale.id === current) ? current : null));
      })
      .catch(() => setError("Non è stato possibile caricare lo storico vendite."))
      .finally(() => setLoading(false));
  }, [query]);
  useEffect(() => {
    Promise.all([
      request("/catalog/brands/?active=true"),
      request("/catalog/categories/?active=true"),
      request("/catalog/seasons/?active=true"),
      request("/core/locations/?active=true"),
      request("/sales/registers/"),
    ])
      .then(([brands, categories, seasons, locations, registers]) =>
        setOptions({
          brands: listItems(brands),
          categories: listItems(categories),
          seasons: listItems(seasons),
          locations: listItems(locations),
          registers: listItems(registers),
        }),
      )
      .catch(() => {});
  }, []);
  useEffect(() => {
    const onKey = (event) => {
      if (event.key === "Escape" && selectedId && !periodOpen) setSelectedId(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, periodOpen]);
  const selected = sales.find((sale) => sale.id === selectedId) || null;
  const confirmed = sales.filter((sale) => sale.status === "CONFIRMED");
  const confirmedTotal = confirmed.reduce((sum, sale) => sum + Number(sale.final_total_amount || 0), 0);
  const activeQuick = QUICK_PERIODS.find(([preset]) => {
    const [from, to] = periodRange(preset);
    return filters.dateFrom === asInputDate(from) && filters.dateTo === asInputDate(to);
  })?.[0];
  function quickPeriod(preset) {
    if (!preset) return setFilters((current) => ({ ...current, dateFrom: "", dateTo: "" }));
    const [from, to] = periodRange(preset);
    setFilters((current) => ({ ...current, dateFrom: asInputDate(from), dateTo: asInputDate(to) }));
  }
  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }
  function setPreset(preset) {
    const [from, to] = periodRange(preset);
    setPeriodDraft({ dateFrom: asInputDate(from), dateTo: asInputDate(to), preset });
  }
  function applyPeriod() {
    setFilters((current) => ({ ...current, dateFrom: periodDraft.dateFrom, dateTo: periodDraft.dateTo }));
    setPeriodOpen(false);
  }
  function clearPeriod() {
    setPeriodDraft({ dateFrom: "", dateTo: "", preset: "" });
    setFilters((current) => ({ ...current, dateFrom: "", dateTo: "" }));
    setPeriodOpen(false);
  }
  async function exportCsv() {
    try {
      await downloadFile(`/sales/sales/export-csv/?${query}`, "vendite.csv");
    } catch (downloadError) {
      setError(downloadError.message);
    }
  }
  return (
    <section className="sales-page history-page">
      <div className="page-title-row">
        <div>
          <p className="eyebrow">Operatività</p>
          <h2>Storico vendite</h2>
          <span>Ricerca gli scontrini e apri una vendita per avviare un reso.</span>
        </div>
        <button className="secondary-action csv-button" onClick={exportCsv}>
          <Download size={17} /> Scarica CSV
        </button>
      </div>
      <div className="history-toolbar">
        <label className="sales-search">
          <Search size={18} />
          <input
            value={filters.search}
            onChange={(event) => updateFilter("search", event.target.value)}
            placeholder="Cerca scontrino, cliente, marca, SKU o barcode"
          />
        </label>
        <button
          className={`history-tool-button ${filters.dateFrom || filters.dateTo ? "active" : ""}`}
          onClick={() => {
            setPeriodDraft({ dateFrom: filters.dateFrom, dateTo: filters.dateTo, preset: "" });
            setPeriodOpen(true);
          }}
        >
          <CalendarDays size={17} /> Periodo <ChevronDown size={15} />
        </button>
        <button
          className={`history-tool-button ${filtersOpen ? "active" : ""}`}
          onClick={() => setFiltersOpen((open) => !open)}
        >
          <Filter size={17} /> Filtri <ChevronDown size={15} />
        </button>
      </div>
      <div className="history-quickbar">
        <div className="seg" role="group" aria-label="Periodi rapidi">
          {QUICK_PERIODS.map(([preset, label]) => (
            <button
              key={preset}
              type="button"
              aria-pressed={activeQuick === preset}
              onClick={() => quickPeriod(preset)}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            aria-pressed={!filters.dateFrom && !filters.dateTo}
            onClick={() => quickPeriod("")}
          >
            Sempre
          </button>
        </div>
        {!loading && !error && (
          <span className="history-summary">
            <b>{confirmed.length}</b> {confirmed.length === 1 ? "vendita conclusa" : "vendite concluse"} ·{" "}
            <b>{euro.format(confirmedTotal)}</b>
          </span>
        )}
      </div>
      {filtersOpen && (
        <div className="history-filters-panel">
          <SelectField
            label="Stato"
            value={filters.status === "ALL" ? "" : filters.status}
            onChange={(value) => updateFilter("status", value || "ALL")}
            options={[
              { value: "OPEN", label: "Aperte" },
              { value: "CONFIRMED", label: "Concluse" },
              { value: "CANCELLED", label: "Annullate" },
            ]}
          />
          <SelectField
            label="Canale"
            value={filters.channel}
            onChange={(value) => updateFilter("channel", value)}
            options={[
              { value: "POS", label: "Negozio" },
              { value: "SHOPIFY", label: "Shopify" },
            ]}
          />
          <SelectField
            label="Sede"
            value={filters.location}
            onChange={(value) => updateFilter("location", value)}
            options={options.locations}
          />
          <SelectField
            label="Cassa"
            value={filters.cashRegister}
            onChange={(value) => updateFilter("cashRegister", value)}
            options={options.registers}
          />
          <SelectField
            label="Marca"
            value={filters.brand}
            onChange={(value) => updateFilter("brand", value)}
            options={options.brands}
          />
          <SelectField
            label="Categoria"
            value={filters.category}
            onChange={(value) => updateFilter("category", value)}
            options={options.categories}
          />
          <SelectField
            label="Stagione"
            value={filters.season}
            onChange={(value) => updateFilter("season", value)}
            options={options.seasons}
          />
          <SelectField
            label="Pagamento"
            value={filters.paymentMethod}
            onChange={(value) => updateFilter("paymentMethod", value)}
            options={[
              { value: "CASH", label: "Contanti" },
              { value: "CARD", label: "Carta" },
              { value: "GIFT_CARD", label: "Gift card" },
              { value: "STORE_CREDIT", label: "Buono reso" },
              { value: "OTHER", label: "Altro" },
            ]}
          />
          <button className="clear-history-filters" onClick={() => setFilters(initialFilters)}>
            Azzera filtri
          </button>
        </div>
      )}
      {periodOpen && (
        <div className="period-layer" role="dialog" aria-modal="true" aria-label="Seleziona periodo">
          <button className="period-backdrop" aria-label="Chiudi" onClick={() => setPeriodOpen(false)} />
          <aside className="period-drawer">
            <header>
              <div>
                <p className="eyebrow">Storico vendite</p>
                <h3>Seleziona periodo</h3>
              </div>
              <button aria-label="Chiudi" onClick={() => setPeriodOpen(false)}>
                <X size={20} />
              </button>
            </header>
            <div className="period-dates">
              <label>
                <span>Data inizio</span>
                <input
                  type="date"
                  value={periodDraft.dateFrom}
                  onChange={(event) =>
                    setPeriodDraft((current) => ({ ...current, dateFrom: event.target.value, preset: "" }))
                  }
                />
              </label>
              <label>
                <span>Data fine</span>
                <input
                  type="date"
                  value={periodDraft.dateTo}
                  onChange={(event) =>
                    setPeriodDraft((current) => ({ ...current, dateTo: event.target.value, preset: "" }))
                  }
                />
              </label>
            </div>
            <div className="period-presets">
              <h4>Periodi preimpostati</h4>
              {[
                ["TODAY", "Oggi"],
                ["YESTERDAY", "Ieri"],
                ["LAST_7", "Ultimi 7 giorni"],
                ["CURRENT_WEEK", "Settimana corrente"],
                ["PREVIOUS_WEEK", "Settimana scorsa"],
                ["CURRENT_MONTH", "Mese corrente"],
                ["PREVIOUS_MONTH", "Mese scorso"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  className={periodDraft.preset === value ? "selected" : ""}
                  onClick={() => setPreset(value)}
                >
                  <i />
                  {label}
                </button>
              ))}
            </div>
            <footer>
              <button className="secondary-action" onClick={clearPeriod}>
                Azzera
              </button>
              <button className="primary-action" onClick={applyPeriod}>
                Applica filtro
              </button>
            </footer>
          </aside>
        </div>
      )}
      <div className={`sales-split${selected ? " has-detail" : ""}`}>
        <article className="sales-list-panel">
          <div className="sales-list-heading">
            <span>Vendita</span>
            <span>Stato</span>
            <span>Totale</span>
          </div>
          {loading && <p className="sales-empty">Caricamento vendite...</p>}
          {error && <p className="sales-error">{error}</p>}
          {!loading && !error && !sales.length && (
            <p className="sales-empty">Nessuna vendita corrisponde ai filtri scelti.</p>
          )}
          {!loading && !error && sales.length > 0 && (
            <PaginatedRows items={sales} resetKey={query}>
              {(rows) =>
                rows.map((sale) => (
                  <button
                    className={`sales-list-row sales-record${sale.id === selectedId ? " selected" : ""}`}
                    key={sale.id}
                    title="Apri il dettaglio della vendita"
                    aria-pressed={sale.id === selectedId}
                    onClick={() => setSelectedId(sale.id === selectedId ? null : sale.id)}
                  >
                    <div>
                      <strong>{sale.number || "Bozza senza numero"}</strong>
                      <span>
                        {sale.customer_name || "Vendita banco"} ·{" "}
                        {dateFormatter.format(new Date(sale.confirmed_at || sale.opened_at))}
                        {piecesOf(sale)
                          ? ` · ${piecesOf(sale)} ${piecesOf(sale) === 1 ? "pezzo" : "pezzi"}`
                          : ""}
                        {methodsOf(sale) ? ` · ${methodsOf(sale)}` : ""}
                      </span>
                    </div>
                    <span className={`status-pill ${sale.status.toLowerCase()}`}>
                      {statusLabel(sale.status)}
                    </span>
                    <strong>{euro.format(Number(sale.final_total_amount))}</strong>
                  </button>
                ))
              }
            </PaginatedRows>
          )}
        </article>
        {selected && (
          <aside className="sale-detail" aria-label={`Dettaglio vendita ${selected.number || ""}`}>
            <header>
              <div>
                <p className="eyebrow">Dettaglio vendita</p>
                <h3>{selected.number || "Bozza senza numero"}</h3>
                <span>{dateFormatter.format(new Date(selected.confirmed_at || selected.opened_at))}</span>
              </div>
              <button
                type="button"
                className="sale-detail-close"
                aria-label="Chiudi"
                onClick={() => setSelectedId(null)}
              >
                <X size={18} />
              </button>
            </header>
            <dl className="sale-detail-facts">
              <div>
                <dt>Stato</dt>
                <dd>
                  <span className={`status-pill ${selected.status.toLowerCase()}`}>
                    {statusLabel(selected.status)}
                  </span>
                </dd>
              </div>
              <div>
                <dt>Cliente</dt>
                <dd>{selected.customer_name || "Vendita banco"}</dd>
              </div>
              <div>
                <dt>Cassa</dt>
                <dd>
                  {[selected.cash_register_name, selected.location_name].filter(Boolean).join(" · ") || "—"}
                </dd>
              </div>
              <div>
                <dt>Pagamento</dt>
                <dd>{methodsOf(selected) || "—"}</dd>
              </div>
            </dl>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Articolo</th>
                  <th>Taglia</th>
                  <th className="num">Q.tà</th>
                  <th className="num">Prezzo</th>
                </tr>
              </thead>
              <tbody>
                {(selected.lines || []).map((line) => (
                  <tr key={line.id}>
                    <td>
                      <b>{line.product_name_snapshot}</b>
                      <small className="sale-line-sku">
                        {[line.sku_snapshot, line.color_snapshot].filter(Boolean).join(" · ")}
                      </small>
                    </td>
                    <td>{line.size_snapshot || "—"}</td>
                    <td className="num">{line.quantity}</td>
                    <td className="num">
                      {euro.format(
                        Number(line.final_unit_price ?? line.base_unit_price ?? 0) *
                          Number(line.quantity || 0),
                      )}
                      {Number(line.discount_amount) > 0 && (
                        <small className="sale-line-discount">
                          sconto {euro.format(Number(line.discount_amount))}
                        </small>
                      )}
                    </td>
                  </tr>
                ))}
                {!(selected.lines || []).length && (
                  <tr>
                    <td colSpan={4} className="empty-note">
                      Nessun articolo in questa vendita.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            <div className="sale-detail-totals">
              {Number(selected.discount_amount) > 0 && (
                <div>
                  <span>Sconti</span>
                  <span>−{euro.format(Number(selected.discount_amount))}</span>
                </div>
              )}
              <div className="total">
                <span>Totale</span>
                <b>{euro.format(Number(selected.final_total_amount || 0))}</b>
              </div>
              {(selected.payments || []).map((payment) => (
                <div key={payment.id}>
                  <span>{METHOD_LABELS[payment.method] || payment.method}</span>
                  <span>{euro.format(Number(payment.amount || 0))}</span>
                </div>
              ))}
            </div>
            {selected.status === "CONFIRMED" ? (
              <button
                type="button"
                className="primary-action sale-detail-return"
                onClick={() => onStartReturn?.(selected)}
              >
                <RotateCcw size={17} /> Avvia un reso
              </button>
            ) : (
              <p className="sale-detail-note">Un reso richiede una vendita conclusa.</p>
            )}
          </aside>
        )}
      </div>
      <div className="sales-count">
        <ShoppingBag size={16} /> {sales.length} vendite visualizzate
      </div>
    </section>
  );
}
