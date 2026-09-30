import { useEffect, useMemo, useState } from "react";
import { request } from "../api";

export const variantLabel = (variant) => [variant.product_name, variant.size_label, variant.color_name, variant.sku].filter(Boolean).join(" · ");

export default function GiftListCatalogPicker({ existingIds, saving, onAdd, onCancel }) {
  const [variants, setVariants] = useState([]);
  const [query, setQuery] = useState("");
  const [selection, setSelection] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const entries = [];
        for (let page = 1; ; page += 1) {
          const data = await request(`/catalog/variants/?is_active=True&page_size=200&page=${page}`);
          entries.push(...(data.results || data));
          if (!data.next) break;
        }
        if (active) setVariants(entries.filter((variant) => variant.is_active));
      } catch (exception) { if (active) setError(exception.message); }
      finally { if (active) setLoading(false); }
    }
    load();
    return () => { active = false; };
  }, []);
  const existing = new Set(existingIds);
  const visible = useMemo(() => variants.filter((variant) => variantLabel(variant).toLowerCase().includes(query.trim().toLowerCase())), [variants, query]);
  const available = visible.filter((variant) => !existing.has(variant.id));
  const allSelected = available.length > 0 && available.every((variant) => selection[variant.id] !== undefined);
  const toggle = (id) => setSelection((current) => {
    const next = { ...current };
    if (next[id] !== undefined) delete next[id]; else next[id] = 1;
    return next;
  });
  const toggleAll = () => setSelection((current) => {
    const next = { ...current };
    available.forEach((variant) => { if (allSelected) delete next[variant.id]; else next[variant.id] ??= 1; });
    return next;
  });
  return <form className="gift-catalog-picker" onSubmit={(event) => { event.preventDefault(); onAdd(Object.entries(selection).map(([variant, quantity]) => ({ variant, quantity: Number(quantity) })), variants); }}>
    <fieldset disabled={saving}>
      <input className="gift-catalog-search" autoFocus aria-label="Cerca nel catalogo" placeholder="Cerca nome, SKU, taglia o colore" value={query} onChange={(event) => setQuery(event.target.value)} />
      {loading ? <p>Caricamento catalogo…</p> : error ? <p className="catalog-error" role="alert">{error}</p> : <>
        <label className="gift-catalog-select-all"><input type="checkbox" checked={allSelected} disabled={!available.length} onChange={toggleAll} /> Seleziona tutti i risultati</label>
        <div className="gift-catalog-options">{visible.map((variant) => <div className="gift-catalog-option" key={variant.id}>
          <label><input type="checkbox" disabled={existing.has(variant.id)} checked={existing.has(variant.id) || selection[variant.id] !== undefined} onChange={() => toggle(variant.id)} /><span>{variantLabel(variant)}{existing.has(variant.id) && <small>Già nella lista</small>}</span></label>
          {selection[variant.id] !== undefined && <label className="gift-catalog-quantity">Quantità<input type="number" required min="1" max="2147483647" step="1" value={selection[variant.id]} onChange={(event) => setSelection((current) => ({ ...current, [variant.id]: event.target.value }))} /></label>}
        </div>)}{!visible.length && <p>Nessun articolo trovato.</p>}</div>
      </>}
      <div className="gift-contribution-actions"><button type="button" className="secondary-action" onClick={onCancel}>Annulla</button><button className="primary-action" disabled={loading || Boolean(error) || !Object.keys(selection).length}>{saving ? "Salvataggio…" : `Aggiungi alla lista (${Object.keys(selection).length})`}</button></div>
    </fieldset>
  </form>;
}
