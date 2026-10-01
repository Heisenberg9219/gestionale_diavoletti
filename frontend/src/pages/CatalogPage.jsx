import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Download, PackagePlus, Plus, Search, Trash2, X } from "lucide-react";
import { downloadFile, request } from "../api";
import PaginationControls from "../components/PaginationControls";
import "../products.css";

const list = (data) => data?.results || data || [];
const currentYear = String(new Date().getFullYear());
const blank = {
  code: "", name: "", description: "", brand: "", category: "", tax_rate: "",
  season_type: "", season_year: currentYear, sku: "", size: "", color: "",
  barcode: "", barcodeId: "", sale_price: "", current_sale_price: "",
};
const blankBulk = { brand: "", category: "", color: "", size: "", sale_price: "", season_type: "", season_year: currentYear };
const Field = ({ label, children }) => <label className="catalog-field"><span>{label}</span>{children}</label>;

const seasonLabel = (type) => ({ SPRING_SUMMER: "Primavera/Estate", AUTUMN_WINTER: "Autunno/Inverno" }[type] || "Altro");
const seasonCode = (type, year) => `${type === "SPRING_SUMMER" ? "PE" : type === "AUTUMN_WINTER" ? "AI" : "ALTRO"}-${year}`;

export default function CatalogPage() {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [total, setTotal] = useState(0);
  const [sort, setSort] = useState({ field: "", direction: "asc" });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blank);
  const [options, setOptions] = useState({ brands: [], categories: [], seasons: [], taxes: [], sizes: [], colors: [] });
  const [saving, setSaving] = useState(false);
  const [skuLoading, setSkuLoading] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState([]);
  const [bulk, setBulk] = useState(blankBulk);
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkNotice, setBulkNotice] = useState("");

  const load = (requestedPage = page, requestedPageSize = pageSize, requestedSort = sort) => {
    setLoading(true);
    const sortParams = requestedSort.field ? `&sort=${requestedSort.field}&sort_direction=${requestedSort.direction}` : "";
    request(`/catalog/variants/?active=true&search=${encodeURIComponent(query)}&page=${requestedPage}&page_size=${requestedPageSize}${sortParams}`)
      .then((data) => {
        const rows = list(data);
        setItems(rows); setTotal(data.count ?? rows.length); setPage(requestedPage);
        setSelected((current) => current.filter((id) => rows.some((item) => item.id === id)));
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load(1, 25);
    Promise.all([
      request("/catalog/brands/?active=true"), request("/catalog/categories/?active=true"),
      request("/catalog/seasons/?active=true"), request("/core/tax-rates/?is_active=true"),
      request("/catalog/sizes/?active=true"), request("/catalog/colors/?active=true"),
    ]).then(([brands, categories, seasons, taxes, sizes, colors]) => {
      setOptions({ brands: list(brands), categories: list(categories), seasons: list(seasons), taxes: list(taxes), sizes: list(sizes), colors: list(colors) });
    }).catch((requestError) => setError(requestError.message));
  }, []);

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const updateBulk = (key, value) => setBulk((current) => ({ ...current, [key]: value }));
  const close = () => { if (!saving && !skuLoading) { setOpen(false); setEditing(null); setError(""); } };
  const toggleSelected = (id) => setSelected((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  const selectedAll = items.length > 0 && items.every((item) => selected.includes(item.id));
  const changePage = (nextPage) => load(nextPage);
  const changePageSize = (nextPageSize) => load(1, nextPageSize);
  const toggleSort = (field) => {
    const nextSort = { field, direction: sort.field === field && sort.direction === "asc" ? "desc" : "asc" };
    setSort(nextSort);
    load(1, pageSize, nextSort);
  };
  const SortLabel = ({ field, children }) => {
    const active = sort.field === field;
    const Icon = active ? (sort.direction === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
    return <button type="button" className={`catalog-sort${active ? " active" : ""}`} onClick={() => toggleSort(field)} aria-label={`Ordina per ${children}`}><span>{children}</span><Icon size={12} /></button>;
  };

  async function ensureSeason(type, year) {
    if (!type) return null;
    const normalizedYear = Number(year) || new Date().getFullYear();
    const found = options.seasons.find((season) => season.season_type === type && Number(season.year) === normalizedYear);
    if (found) return found.id;
    const created = await request("/catalog/seasons/", {
      method: "POST",
      body: JSON.stringify({ code: seasonCode(type, normalizedYear), name: `${seasonLabel(type)} ${normalizedYear}`, season_type: type, year: normalizedYear }),
    });
    setOptions((current) => ({ ...current, seasons: [...current.seasons, created] }));
    return created.id;
  }

  async function quickAdd(kind, target = "form") {
    const labels = { brands: "della marca", categories: "della categoria", colors: "del colore" };
    const name = window.prompt(`Nome ${labels[kind]}`)?.trim();
    if (!name) return;
    const code = `${name.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 20) || "NUOVO"}_${Date.now().toString().slice(-5)}`;
    try {
      const created = await request({ brands: "/catalog/brands/", categories: "/catalog/categories/", colors: "/catalog/colors/" }[kind], {
        method: "POST", body: JSON.stringify({ code, name }),
      });
      setOptions((current) => ({ ...current, [kind]: [...current[kind], created] }));
      const field = { brands: "brand", categories: "category", colors: "color" }[kind];
      if (target === "bulk") updateBulk(field, created.id);
      else update(field, created.id);
    } catch (requestError) { setError(requestError.message); }
  }

  async function openEdit(item) {
    setSkuLoading(false);
    try {
      const [product, codes, prices] = await Promise.all([
        request(`/catalog/products/${item.product}/`), request(`/catalog/barcodes/?variant=${item.id}`),
        request(`/pricing/sale-prices/?variant=${item.id}&current=true`),
      ]);
      const barcode = list(codes)[0];
      const price = list(prices)[0];
      const season = options.seasons.find((entry) => entry.id === product.season);
      setEditing(item);
      setForm({
        code: product.code, name: product.name, description: product.description || "", brand: product.brand || "", category: product.category || "", tax_rate: product.tax_rate || "",
        season_type: season?.season_type || "", season_year: season?.year ? String(season.year) : currentYear,
        sku: item.sku, size: item.size, color: item.color || "", barcode: barcode?.code || "", barcodeId: barcode?.id || "",
        sale_price: price?.amount || "", current_sale_price: price?.amount || "",
      });
      setOpen(true);
    } catch (requestError) { setError(requestError.message); }
  }

  async function openNew() {
    setEditing(null); setError(""); setForm({ ...blank }); setOpen(true); setSkuLoading(true);
    try {
      const result = await request("/catalog/variants/reserve-skus/", { method: "POST", body: JSON.stringify({ count: 1 }) });
      if (!result.skus?.[0]) throw new Error("Non è stato possibile generare il prossimo SKU.");
      setForm((current) => ({ ...current, sku: result.skus[0] }));
    } catch (requestError) { setError(requestError.message); }
    finally { setSkuLoading(false); }
  }

  async function save(event) {
    event.preventDefault();
    setSaving(true); setError("");
    try {
      const season = await ensureSeason(form.season_type, form.season_year);
      const productData = { code: form.code, name: form.name, description: form.description, brand: form.brand || null, category: form.category, season, tax_rate: form.tax_rate };
      let variantId = editing?.id;
      if (editing) {
        await request(`/catalog/products/${editing.product}/`, { method: "PATCH", body: JSON.stringify(productData) });
        await request(`/catalog/variants/${editing.id}/`, { method: "PATCH", body: JSON.stringify({ sku: form.sku, size: form.size, color: form.color || null }) });
      } else {
        const product = await request("/catalog/products/", { method: "POST", body: JSON.stringify(productData) });
        const variant = await request("/catalog/variants/", { method: "POST", body: JSON.stringify({ product: product.id, sku: form.sku, size: form.size, color: form.color || null }) });
        variantId = variant.id;
      }
      if (form.barcode.trim()) {
        await request(form.barcodeId ? `/catalog/barcodes/${form.barcodeId}/` : "/catalog/barcodes/", {
          method: form.barcodeId ? "PATCH" : "POST",
          body: JSON.stringify(form.barcodeId ? { code: form.barcode.trim() } : { variant: variantId, code: form.barcode.trim(), barcode_type: "OTHER", source: "INTERNAL", is_primary: true, is_active: true }),
        });
      } else if (form.barcodeId) await request(`/catalog/barcodes/${form.barcodeId}/`, { method: "DELETE" });
      if (form.sale_price && form.sale_price !== form.current_sale_price) {
        await request("/pricing/sale-prices/", { method: "POST", body: JSON.stringify({ variant: variantId, amount: form.sale_price, source: "MANUAL" }) });
      }
      setOpen(false); setEditing(null); setForm(blank); load();
    } catch (requestError) { setError(requestError.message); } finally { setSaving(false); }
  }

  async function applyBulk() {
    const changes = Object.fromEntries(Object.entries(bulk).filter(([key, value]) => value !== "" && key !== "season_type" && key !== "season_year"));
    if (!Object.keys(changes).length && !bulk.season_type) { setError("Seleziona almeno un valore da modificare."); return; }
    setBulkSaving(true); setError(""); setBulkNotice("");
    try {
      if (bulk.season_type) changes.season = await ensureSeason(bulk.season_type, bulk.season_year);
      const result = await request("/catalog/variants/bulk-update/", { method: "POST", body: JSON.stringify({ variants: selected, changes }) });
      setBulkNotice(`${result.updated} righe aggiornate correttamente.`); setBulk(blankBulk); load();
    } catch (requestError) { setError(requestError.message); } finally { setBulkSaving(false); }
  }

  async function archiveBulk() {
    if (!window.confirm(`Vuoi cancellare ${selected.length} righe dal catalogo? Le varianti saranno archiviate e non più visibili.`)) return;
    setBulkSaving(true); setError(""); setBulkNotice("");
    try {
      const result = await request("/catalog/variants/bulk-archive/", { method: "POST", body: JSON.stringify({ variants: selected }) });
      setBulkNotice(`${result.archived} righe cancellate dal catalogo.`); setSelected([]); load();
    } catch (requestError) { setError(requestError.message); } finally { setBulkSaving(false); }
  }

  async function exportBulk() {
    try { await downloadFile("/catalog/variants/export-csv/", "catalogo-selezionato.csv", { method: "POST", body: JSON.stringify({ variants: selected }) }); }
    catch (requestError) { setError(requestError.message); }
  }

  return <section className="products-page">
    <div className="page-title-row"><div><p className="eyebrow">Prodotti</p><h2>Catalogo</h2><span>Clicca sul titolo dell’articolo per modificarlo.</span></div><button className="primary-action" onClick={openNew}><PackagePlus size={17} /> Nuovo articolo</button></div>
    <form className="products-search" onSubmit={(event) => { event.preventDefault(); load(1); }}><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Cerca nome, SKU, barcode o codice prodotto" /><button>Ricerca</button></form>
    {error && !open && <p className="catalog-error">{error}</p>}
    {selected.length > 0 && <section className="catalog-bulk-panel">
      <div className="catalog-bulk-heading"><strong>{selected.length} righe selezionate</strong><span>Applica solo i campi compilati.</span></div>
      <div className="catalog-bulk-fields">
        <Field label="Marca"><span className="select-with-add"><select value={bulk.brand} onChange={(event) => updateBulk("brand", event.target.value)}><option value="">Non modificare</option>{options.brands.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button type="button" onClick={() => quickAdd("brands", "bulk")} title="Aggiungi marca"><Plus size={16} /></button></span></Field>
        <Field label="Categoria"><span className="select-with-add"><select value={bulk.category} onChange={(event) => updateBulk("category", event.target.value)}><option value="">Non modificare</option>{options.categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button type="button" onClick={() => quickAdd("categories", "bulk")} title="Aggiungi categoria"><Plus size={16} /></button></span></Field>
        <Field label="Tipo collezione"><select value={bulk.season_type} onChange={(event) => updateBulk("season_type", event.target.value)}><option value="">Non modificare</option><option value="SPRING_SUMMER">Primavera/Estate</option><option value="AUTUMN_WINTER">Autunno/Inverno</option></select></Field>
        <Field label="Anno collezione"><input type="number" min="2000" max="2100" disabled={!bulk.season_type} value={bulk.season_year} onChange={(event) => updateBulk("season_year", event.target.value)} /></Field>
        <Field label="Colore"><span className="select-with-add"><select value={bulk.color} onChange={(event) => updateBulk("color", event.target.value)}><option value="">Non modificare</option>{options.colors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button type="button" onClick={() => quickAdd("colors", "bulk")} title="Aggiungi colore"><Plus size={16} /></button></span></Field>
        <Field label="Taglia"><select value={bulk.size} onChange={(event) => updateBulk("size", event.target.value)}><option value="">Non modificare</option>{options.sizes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></Field>
        <Field label="Prezzo vendita"><input type="number" min="0.01" step="0.01" value={bulk.sale_price} onChange={(event) => updateBulk("sale_price", event.target.value)} placeholder="Non modificare" /></Field>
      </div>
      <div className="catalog-bulk-actions"><button className="secondary-action" type="button" disabled={bulkSaving} onClick={exportBulk}><Download size={16} /> Scarica CSV</button><button className="secondary-action catalog-delete-action" type="button" disabled={bulkSaving} onClick={archiveBulk}><Trash2 size={16} /> Cancella selezionati</button><button className="primary-action" type="button" disabled={bulkSaving} onClick={applyBulk}>{bulkSaving ? "Salvataggio..." : "Applica modifiche"}</button></div>
    </section>}
    {bulkNotice && <p className="operation-success">{bulkNotice}</p>}
    <article className="products-list catalog-table">
      <div className="catalog-heading"><span><input aria-label="Seleziona tutte le righe" type="checkbox" checked={selectedAll} onChange={() => setSelected(selectedAll ? [] : items.map((item) => item.id))} /></span><span>Articolo</span><span><SortLabel field="brand">Marca</SortLabel></span><span><SortLabel field="category">Categoria</SortLabel></span><span><SortLabel field="season">Collezione</SortLabel></span><span>IVA</span><span><SortLabel field="sku">SKU</SortLabel></span><span>Variante</span><span>Barcode</span></div>
      {loading ? <p>Caricamento catalogo...</p> : items.map((item) => <div className="catalog-row" key={item.id}><span><input aria-label={`Seleziona ${item.product_name}`} type="checkbox" checked={selected.includes(item.id)} onChange={() => toggleSelected(item.id)} /></span><div><button className="catalog-title" onClick={() => openEdit(item)}>{item.product_name}</button><span>{item.product_code}</span></div><span>{item.brand_name || "—"}</span><span>{item.category_name || "—"}</span><span>{item.season_name || "—"}</span><span>{item.tax_rate_name || "—"}</span><b>{item.sku}</b><span>{[item.color_name, item.size_label].filter(Boolean).join(" · ") || "—"}</span><span>{item.barcodes?.join(", ") || "—"}</span></div>)}
    </article>
    {!loading && <PaginationControls page={page} pageSize={pageSize} total={total} onPageChange={changePage} onPageSizeChange={changePageSize} />}
    {open && <div className="catalog-modal-layer"><button className="catalog-modal-backdrop" onClick={close} /><form className="catalog-modal" onSubmit={save}><header><div><p className="eyebrow">Catalogo</p><h3>{editing ? "Modifica articolo" : "Nuovo articolo"}</h3></div><button type="button" onClick={close}><X size={19} /></button></header>{error && <p className="catalog-error">{error}</p>}<div className="catalog-form-grid">
      <Field label="Codice prodotto"><input required value={form.code} onChange={(event) => update("code", event.target.value)} /></Field><Field label="Nome prodotto"><input required value={form.name} onChange={(event) => update("name", event.target.value)} /></Field>
      <Field label="Descrizione"><input value={form.description} onChange={(event) => update("description", event.target.value)} /></Field><Field label="Tipo collezione"><select value={form.season_type} onChange={(event) => update("season_type", event.target.value)}><option value="">Nessuna</option><option value="SPRING_SUMMER">Primavera/Estate</option><option value="AUTUMN_WINTER">Autunno/Inverno</option></select></Field>
      <Field label="Anno collezione"><input type="number" min="2000" max="2100" disabled={!form.season_type} value={form.season_year} onChange={(event) => update("season_year", event.target.value)} /></Field>
      {[ ["Marca", "brands", "brand", false], ["Categoria", "categories", "category", true] ].map(([label, kind, key, required]) => <Field key={key} label={label}><span className="select-with-add"><select required={required} value={form[key]} onChange={(event) => update(key, event.target.value)}><option value="">{required ? "Seleziona" : "Nessuna"}</option>{options[kind].map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button type="button" onClick={() => quickAdd(kind)}><Plus size={16} /></button></span></Field>)}
      <Field label="IVA"><select required value={form.tax_rate} onChange={(event) => update("tax_rate", event.target.value)}><option value="">Seleziona</option>{options.taxes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><Field label="SKU"><input required disabled={!editing && skuLoading} value={form.sku} placeholder={skuLoading ? "Generazione SKU..." : "SKU progressivo"} onChange={(event) => update("sku", event.target.value)} /></Field>
      <Field label="Taglia"><select required value={form.size} onChange={(event) => update("size", event.target.value)}><option value="">Seleziona</option>{options.sizes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></Field><Field label="Colore"><span className="select-with-add"><select value={form.color} onChange={(event) => update("color", event.target.value)}><option value="">Nessuno</option>{options.colors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button type="button" onClick={() => quickAdd("colors")}><Plus size={16} /></button></span></Field>
      <Field label="Prezzo vendita"><input required type="number" min="0.01" step="0.01" value={form.sale_price} onChange={(event) => update("sale_price", event.target.value)} /></Field><Field label="Barcode"><input value={form.barcode} onChange={(event) => update("barcode", event.target.value)} /></Field>
    </div><footer><button type="button" className="secondary-action" onClick={close}>Annulla</button><button className="primary-action" disabled={saving || skuLoading}>{saving ? "Salvataggio..." : skuLoading ? "Generazione SKU..." : "Salva modifiche"}</button></footer></form></div>}
  </section>;
}
