import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Eye, FileText, FileUp, Plus, ScanText, Search, X } from "lucide-react";
import { request } from "../api";
import "../products.css";
import "./DocumentsOcrPage.css";

const list = (data) => data?.results || data || [];
async function allPages(path) {
  const rows = [];
  for (let page = 1; ; page += 1) {
    const data = await request(`${path}${path.includes("?") ? "&" : "?"}page=${page}&page_size=200`);
    rows.push(...list(data));
    if (!data.next) return rows;
  }
}
const today = () => new Date().toISOString().slice(0, 10);
const blank = () => ({ document_type: "", title: "", number: "", document_date: today(), counterparty_name: "", file: null });
const statusLabel = { DRAFT: "Bozza", REGISTERED: "Registrato", ISSUED: "Emesso", CANCELLED: "Annullato" };
const directionLabel = { INCOMING: "Ricevuto", OUTGOING: "Emesso", INTERNAL: "Interno" };
const date = (value) => value ? new Intl.DateTimeFormat("it-IT").format(new Date(`${value}T00:00:00`)) : "Non indicata";
const amount = (value) => Number.parseFloat(String(value).replace(",", ".")) || 0;
const money = (value) => amount(value).toFixed(2);
const lineTotal = (item) => amount(item.quantity) * amount(item.unit_price);


function latest(items, attachment) {
  return items.filter((item) => item.attachment === attachment && item.status === "SUCCEEDED").sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0];
}

function makeReview(analysis) {
  const proposal = analysis.proposed_data || {};
  const saved = proposal.review || {};
  return {
    ...saved,
    supplier_name: saved.supplier_name ?? proposal.supplier_name ?? "",
    invoice_number: saved.invoice_number ?? proposal.invoice_number ?? "",
    invoice_date: saved.invoice_date ?? proposal.invoice_date ?? "",
    supplier_id: saved.supplier_id ?? saved.supplier ?? "",
    location_id: saved.location_id ?? saved.location ?? "",
    taxable_amount: saved.taxable_amount ?? proposal.taxable_amount ?? "",
    tax_rate: saved.tax_rate ?? "",
    total_amount: saved.total_amount ?? proposal.total_amount ?? "",
    items: (saved.items ?? proposal.items ?? []).map((row, index) => {
      const item = { ...(proposal.items?.[index] || {}), ...row };
      const previous = item.new_product || {};
      const stored = item.new_variant || {};
      return {
        ...item, accepted: item.accepted ?? true,
        variant_id: item.variant_id ?? ((item.new_product || item.new_variant) ? "__new__" : ""),
        description: item.description ?? "", quantity: item.quantity ?? "", unit_price: item.unit_price ?? "", sale_price: item.sale_price ?? "",
        new_variant: {
          product_id: previous.product_id || "", product_name: previous.name ?? item.description ?? "",
          category_id: previous.category || "", tax_rate_id: previous.tax_rate || "", color_id: previous.color || "", ...stored,
          variants: stored.variants || [{ size_id: stored.size_id || previous.size || "", sku: stored.sku || previous.sku || "", barcode: stored.barcode || previous.barcode || "", quantity: item.quantity ?? "", sale_price: stored.sale_price ?? item.sale_price ?? "" }],
        },
      };
    }),
  };
}

export default function DocumentsOcrPage() {
  const [documents, setDocuments] = useState([]); const [types, setTypes] = useState([]); const [attachments, setAttachments] = useState([]); const [analyses, setAnalyses] = useState([]); const [variants, setVariants] = useState([]); const [suppliers, setSuppliers] = useState([]); const [locations, setLocations] = useState([]); const [catalog, setCatalog] = useState({ products: [], categories: [], taxes: [], colors: [], sizes: [] }); const [markup, setMarkup] = useState("2.5");
  const [query, setQuery] = useState(""); const [formOpen, setFormOpen] = useState(false); const [form, setForm] = useState(blank()); const [saving, setSaving] = useState(false); const [message, setMessage] = useState(""); const [success, setSuccess] = useState(false);
  const [reviewAnalysis, setReviewAnalysis] = useState(null); const [review, setReview] = useState(null); const [reviewSaving, setReviewSaving] = useState(false); const [reviewError, setReviewError] = useState(""); const [reviewNotice, setReviewNotice] = useState("");
  const [conflicts, setConflicts] = useState([]);
  const [issues, setIssues] = useState([]);
  const [bulk, setBulk] = useState({ category: "", tax: "", prices: false });
  const [onlyPending, setOnlyPending] = useState(false);
  const [checking, setChecking] = useState(true);
  const imported = ["IMPORTED", "APPLIED"].includes(review?.status);
  const changeReview = (value) => { setChecking(true); setReview(value); };
  const rowIssues = (index) => issues.filter((issue) => issue.row === index);
  const pendingRows = [...new Set(issues.filter((issue) => issue.row !== null).map((issue) => issue.row))];
  const generalIssues = issues.filter((issue) => issue.row === null);
  const goToPending = () => {
    const target = pendingRows.length ? `ocr-row-${pendingRows[0]}` : "ocr-invoice-fields";
    document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  const applyBulk = () => changeReview((current) => ({ ...current, items: current.items.map((item) => {
    if (!item.accepted || item.variant_id !== "__new__") return item;
    const data = item.new_variant;
    return { ...item, new_variant: { ...data,
      category_id: data.category_id || bulk.category,
      tax_rate_id: data.tax_rate_id || bulk.tax,
      variants: data.variants.map((variant) => ({ ...variant,
        sale_price: bulk.prices && !variant.sale_price && amount(item.unit_price) > 0 ? money(amount(item.unit_price) * amount(markup)) : variant.sale_price,
      })),
    } };
  }) }));
  const notice = (text, ok = true) => { setSuccess(ok); setMessage(text); };
  const load = async () => { try { const [a, b, c, d, e, f, g, h, i, j, k, l, m] = await Promise.all([allPages("/documents/documents/"), allPages("/documents/types/?is_active=True"), allPages("/documents/attachments/"), allPages("/documents/ocr-analyses/"), allPages("/catalog/variants/?page_size=200"), allPages("/suppliers/suppliers/?page_size=200"), allPages("/core/locations/?is_active=True"), allPages("/catalog/products/?is_active=True&page_size=200"), allPages("/catalog/categories/?is_active=True&page_size=200"), allPages("/core/tax-rates/?is_active=True&page_size=100"), allPages("/catalog/colors/?is_active=True&page_size=200"), allPages("/catalog/sizes/?is_active=True&page_size=200"), allPages("/core/settings/")]); setDocuments(list(a)); setTypes(list(b)); setAttachments(list(c)); setAnalyses(list(d)); setVariants(list(e)); setSuppliers(list(f)); setLocations(list(g)); setCatalog({ products: list(h), categories: list(i), taxes: list(j), colors: list(k), sizes: list(l) }); setMarkup(list(m)[0]?.default_markup || "2.5"); } catch (error) { notice(error.message, false); } };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!message) return undefined; const timer = setTimeout(() => setMessage(""), 4000); return () => clearTimeout(timer); }, [message]);

  const visible = useMemo(() => documents.filter((document) => `${document.title} ${document.number} ${document.counterparty_name}`.toLowerCase().includes(query.toLowerCase())), [documents, query]);
  const typeFor = (id) => types.find((item) => item.id === id); const attachmentFor = (id) => attachments.find((item) => item.document === id);
  const closeReview = () => { if (reviewSaving) return; setReviewAnalysis(null); setReview(null); setReviewError(""); setReviewNotice(""); };
  const updateReview = (key, value) => changeReview((current) => ({ ...current, [key]: value }));
  const updateItem = (index, key, value) => changeReview((current) => ({ ...current, items: current.items.map((item, itemIndex) => {
    if (itemIndex !== index) return item;
    const updated = { ...item, [key]: value };
    if (key === "quantity" && item.new_variant.variants.length === 1) {
      updated.new_variant = { ...item.new_variant, variants: [{ ...item.new_variant.variants[0], quantity: value }] };
    }
    return updated;
  }) }));
  const updateNewVariant = (index, key, value) => changeReview((current) => ({ ...current, items: current.items.map((item, itemIndex) => itemIndex === index ? { ...item, new_variant: { ...item.new_variant, [key]: value } } : item) }));
  const updateVariantDetail = (itemIndex, variantIndex, key, value) => changeReview((current) => ({ ...current, items: current.items.map((item, index) => index === itemIndex ? { ...item, new_variant: { ...item.new_variant, variants: (item.new_variant.variants || []).map((variant, variantPosition) => variantPosition === variantIndex ? { ...variant, [key]: value } : variant) } } : item) }));
  const addVariantSize = (itemIndex) => changeReview((current) => ({ ...current, items: current.items.map((item, index) => index === itemIndex ? { ...item, new_variant: { ...item.new_variant, variants: [...(item.new_variant.variants || []), { size_id: "", sku: "", barcode: "", quantity: "", sale_price: "" }] } } : item) }));
  const removeVariantSize = (itemIndex, variantIndex) => changeReview((current) => ({ ...current, items: current.items.map((item, index) => index === itemIndex ? { ...item, new_variant: { ...item.new_variant, variants: item.new_variant.variants.filter((_, position) => position !== variantIndex) } } : item) }));
  async function addCategory(itemIndex) { const name = window.prompt("Nome della nuova categoria")?.trim(); if (!name) return; const code = `${name.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 20) || "CATEGORIA"}_${Date.now().toString().slice(-5)}`; try { const category = await request("/catalog/categories/", { method: "POST", body: JSON.stringify({ code, name }) }); setCatalog((current) => ({ ...current, categories: [...current.categories, category] })); updateNewVariant(itemIndex, "category_id", category.id); } catch (error) { setReviewError(error.message); } }
  async function addColor(itemIndex) { const name = window.prompt("Nome del nuovo colore")?.trim(); if (!name) return; const code = `${name.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 20) || "COLORE"}_${Date.now().toString().slice(-5)}`; try { const color = await request("/catalog/colors/", { method: "POST", body: JSON.stringify({ code, name }) }); setCatalog((current) => ({ ...current, colors: [...current.colors, color] })); updateNewVariant(itemIndex, "color_id", color.id); } catch (error) { setReviewError(error.message); } }
  const reviewSubtotal = review?.items.filter((item) => item.accepted).reduce((total, item) => total + lineTotal(item), 0) || 0;
  const reviewTax = reviewSubtotal * amount(review?.tax_rate) / 100;
  const reviewTotal = reviewSubtotal + reviewTax;

  async function upload(event) { event.preventDefault(); if (!form.file) return notice("Seleziona un PDF da allegare.", false); setSaving(true); try { const type = typeFor(form.document_type); const document = await request("/documents/documents/", { method: "POST", body: JSON.stringify({ document_type: form.document_type, direction: type.direction, status: "DRAFT", number: form.number, document_date: form.document_date, title: form.title, taxable_amount: "0.00", tax_amount: "0.00", total_amount: "0.00", counterparty_name: form.counterparty_name }) }); const data = new FormData(); data.append("file", form.file); data.append("description", "Documento caricato per analisi OCR"); await request(`/documents/documents/${document.id}/upload-attachment/`, { method: "POST", body: data }); setFormOpen(false); setForm(blank()); notice("Documento e PDF caricati. Avvia l'OCR per preparare la proposta."); await load(); } catch (error) { notice(error.message, false); } finally { setSaving(false); } }
  async function analyze(attachment) { try { await request(`/documents/attachments/${attachment.id}/analyze-invoice/`, { method: "POST", body: JSON.stringify({}) }); notice("Analisi OCR completata. Apri la proposta per controllare gli articoli."); await load(); } catch (error) { notice(error.message, false); await load(); } }
  async function finalize(document) { try { await request(`/documents/documents/${document.id}/finalize/`, { method: "POST", body: JSON.stringify({ number: document.number }) }); notice("Documento registrato correttamente."); await load(); } catch (error) { notice(error.message, false); } }
  const draftReview = () => ({ ...review, supplier: review.supplier_id, location: review.location_id });
  const applyReview = () => ({ ...draftReview(), items: review.items.map((item) => ({ ...item, variant_id: item.variant_id === "__new__" ? "" : item.variant_id, new_variant: item.variant_id === "__new__" ? item.new_variant : undefined })) });
  useEffect(() => {
    if (!review || imported) return;
    let active = true;
    setChecking(true);
    const timer = setTimeout(async () => {
      try {
        const result = await request(`/documents/attachments/${reviewAnalysis.attachment}/validate-review/`, { method: "POST", body: JSON.stringify({ review: { ...review, supplier: review.supplier_id, location: review.location_id, items: review.items.map((item) => ({ ...item, new_variant: item.variant_id === "__new__" ? item.new_variant : undefined, new_product: undefined })) } }) });
        if (active) { setConflicts(result.conflicts); setIssues(result.issues || result.conflicts.map((message) => ({ row: null, kind: "incomplete", message }))); setChecking(false); }
      } catch (error) { if (active) { setConflicts([error.message]); setIssues([{ row: null, kind: "incomplete", message: error.message }]); setChecking(false); } }
    }, 350);
    return () => { active = false; clearTimeout(timer); };
  }, [review, reviewAnalysis, imported]);
  async function saveDraft() {
    setReviewSaving(true); setReviewError(""); setReviewNotice("");
    try {
      const saved = await request(`/documents/ocr-analyses/${reviewAnalysis.id}/save-purchase-proposal/`, { method: "POST", body: JSON.stringify({ review: draftReview() }) });
      setReviewAnalysis(saved); changeReview(makeReview(saved));
      setReviewNotice("Proposta salvata. Le giacenze non sono state modificate."); await load();
    } catch (error) { setReviewError(error.message); } finally { setReviewSaving(false); }
  }
  async function saveReview() {
    setReviewSaving(true); setReviewError(""); setReviewNotice("");
    try {
      const proposal = applyReview();
      await request(`/documents/ocr-analyses/${reviewAnalysis.id}/save-purchase-proposal/`, { method: "POST", body: JSON.stringify({ review: draftReview() }) });
      await request(`/documents/ocr-analyses/${reviewAnalysis.id}/apply-purchase-proposal/`, { method: "POST", body: JSON.stringify({ review: proposal, supplier: review.supplier_id, location: review.location_id }) });
      setReviewAnalysis(null); setReview(null); notice("Fattura registrata, Catalogo e Magazzino aggiornati."); await load();
    } catch (error) { setReviewError(error.message); } finally { setReviewSaving(false); }
  }

  return <section className="products-page documents-page">
    <div className="page-title-row"><div><p className="eyebrow">Gestione</p><h2>Documenti e OCR</h2><span>Carica fatture e documenti PDF, poi verifica gli articoli rilevati.</span></div><button className="primary-action" onClick={() => { setForm(blank()); setFormOpen(true); }}><Plus size={17} /> Carica documento</button></div>
    {formOpen && <form className="document-form" onSubmit={upload}><div className="inventory-form-copy document-copy"><p className="eyebrow">Nuovo documento</p><h3>Carica un PDF</h3><span>L'OCR riconosce i dati della fattura dopo il caricamento.</span></div><label>Tipo documento<select required value={form.document_type} onChange={(event) => setForm({ ...form, document_type: event.target.value })}><option value="">Seleziona tipo</option>{types.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Titolo<input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label><label>Numero documento<input value={form.number} onChange={(event) => setForm({ ...form, number: event.target.value })} /></label><label>Data documento<input required type="date" value={form.document_date} onChange={(event) => setForm({ ...form, document_date: event.target.value })} /></label><label>Fornitore<input value={form.counterparty_name} onChange={(event) => setForm({ ...form, counterparty_name: event.target.value })} /></label><label>File PDF<span className="document-file-control"><input id="document-pdf" required type="file" accept="application/pdf" onChange={(event) => setForm({ ...form, file: event.target.files?.[0] || null })} /><button type="button" onClick={() => document.getElementById("document-pdf")?.click()}>Scegli file</button><span>{form.file?.name || "Nessun file selezionato"}</span></span></label><div className="inline-form-actions"><button type="button" className="secondary-action" onClick={() => setFormOpen(false)}>Annulla</button><button className="primary-action" disabled={saving}>{saving ? "Caricamento..." : "Carica"}</button></div></form>}
    {message && <p className={success ? "operation-success" : "catalog-error"}>{message}</p>}
    <div className="voucher-filters"><div className="products-search"><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Cerca documento, numero o fornitore" /></div></div>
    <article className="products-list"><div className="document-heading"><span>Documento</span><span>Tipo</span><span>Data</span><span>PDF e OCR</span><span>Stato</span><span>Azioni</span></div>{!visible.length ? <div className="empty-product-state"><FileText size={28} /><strong>Nessun documento trovato</strong><span>Carica un PDF per costruire l'archivio documentale.</span></div> : visible.map((document) => { const attachment = attachmentFor(document.id); const analysis = attachment && latest(analyses, attachment.id); const reviewed = Boolean(analysis?.proposed_data?.review?.status); return <div className="document-row" key={document.id}><div><strong>{document.title}</strong><span>{document.number || "Numero non indicato"}{document.counterparty_name ? ` · ${document.counterparty_name}` : ""}</span></div><span>{typeFor(document.document_type)?.name || directionLabel[document.direction]}</span><span>{date(document.document_date)}</span><span>{analysis?.status === "SUCCEEDED" ? reviewed ? ["APPLIED", "IMPORTED"].includes(analysis.proposed_data.review.status) ? "Caricato in magazzino" : "Proposta salvata" : "OCR completato" : analysis?.status === "FAILED" ? "OCR non disponibile" : attachment ? "PDF pronto" : "Nessun PDF"}</span><em className={`document-status ${document.status.toLowerCase()}`}>{statusLabel[document.status] || document.status}</em><div className="document-actions">{analysis?.status === "SUCCEEDED" && <button title="Apri proposta OCR" onClick={() => { setReviewAnalysis(analysis); setReviewError(""); setReviewNotice(""); setOnlyPending(false); setIssues([]); changeReview(makeReview(analysis)); }}><Eye size={16} /></button>}{attachment && <button title="Analizza fattura con OCR" onClick={() => analyze(attachment)}><ScanText size={16} /></button>}{document.status === "DRAFT" && reviewed && <button title="Registra documento" onClick={() => finalize(document)}><CheckCircle2 size={16} /></button>}{attachment?.file && <a href={attachment.file} target="_blank" rel="noreferrer" title="Apri PDF"><FileUp size={16} /></a>}</div></div>; })}</article>
    {reviewAnalysis && review && <div className="ocr-review-layer" role="dialog" aria-modal="true"><button className="ocr-review-backdrop" aria-label="Chiudi" onClick={closeReview} /><section className="ocr-review-modal"><header><div><p className="eyebrow">Proposta OCR</p><h3>Controlla e registra la fattura</h3><span>Le righe incluse verranno caricate nel magazzino selezionato.</span></div><button type="button" title="Chiudi" onClick={closeReview}><X size={20} /></button></header>{reviewError && <p className="ocr-review-feedback error">{reviewError}</p>}{reviewNotice && <p className="ocr-review-feedback success">{reviewNotice}</p>}<label className="ocr-conflicts">Versione proposta<select disabled={reviewSaving} value={reviewAnalysis.id} onChange={(event) => { const selected = analyses.find((entry) => entry.id === event.target.value); setReviewError(""); setReviewAnalysis(selected); changeReview(makeReview(selected)); }}>{analyses.filter((entry) => entry.attachment === reviewAnalysis.attachment && entry.status === "SUCCEEDED").map((entry) => <option key={entry.id} value={entry.id}>{new Date(entry.created_at).toLocaleString("it-IT")} · {entry.proposed_data?.review?.status || "OCR"}</option>)}</select></label><fieldset className="ocr-review-fields" disabled={reviewSaving || imported}><div id="ocr-invoice-fields" className="ocr-review-summary"><label>Fornitore<input value={review.supplier_name} onChange={(event) => updateReview("supplier_name", event.target.value)} /></label><label>Fornitore in rubrica<select value={review.supplier_id} onChange={(event) => updateReview("supplier_id", event.target.value)}><option value="">Seleziona fornitore</option>{suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.business_name}</option>)}</select></label><label>Destinazione carico<select value={review.location_id} onChange={(event) => updateReview("location_id", event.target.value)}><option value="">Seleziona sede</option>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label><label>Numero fattura<input value={review.invoice_number} onChange={(event) => updateReview("invoice_number", event.target.value)} /></label><label>Data<input type="date" value={review.invoice_date} onChange={(event) => updateReview("invoice_date", event.target.value)} /></label><label>Imponibile articoli<input inputMode="decimal" value={review.taxable_amount} onChange={(event) => updateReview("taxable_amount", event.target.value)} /></label><label>IVA %<input inputMode="decimal" value={review.tax_rate} onChange={(event) => updateReview("tax_rate", event.target.value)} /></label><label>Totale fattura<input inputMode="decimal" value={review.total_amount} onChange={(event) => updateReview("total_amount", event.target.value)} /></label></div>{!checking && generalIssues.length > 0 && <div className="ocr-header-issues">{generalIssues.map((issue, index) => <p key={index}>{issue.message}</p>)}</div>}<details className="ocr-bulk"><summary>Completa più articoli insieme</summary><p>Applica solo ai campi vuoti dei nuovi articoli inclusi. Le scelte già inserite restano invariate.</p><div className="ocr-bulk-fields"><label>Categoria<select value={bulk.category} onChange={(event) => setBulk({ ...bulk, category: event.target.value })}><option value="">Non modificare</option>{catalog.categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label><label>Aliquota IVA<select value={bulk.tax} onChange={(event) => setBulk({ ...bulk, tax: event.target.value })}><option value="">Non modificare</option>{catalog.taxes.map((tax) => <option key={tax.id} value={tax.id}>{tax.name}</option>)}</select></label><label className="ocr-bulk-checkbox"><input type="checkbox" checked={bulk.prices} onChange={(event) => setBulk({ ...bulk, prices: event.target.checked })} />Calcola prezzi vendita con ricarico ×{markup}</label><button type="button" className="secondary-action" disabled={!bulk.category && !bulk.tax && !bulk.prices} onClick={applyBulk}>Applica ai campi vuoti</button></div></details><div className="ocr-review-toolbar"><strong>{review.items.filter((item) => item.accepted).length} righe incluse</strong><label><input type="checkbox" checked={onlyPending} onChange={(event) => setOnlyPending(event.target.checked)} />Mostra solo da completare</label></div><div className="ocr-review-lines"><div className="ocr-review-heading"><span>Incl.</span><span>Descrizione</span><span>Articolo in catalogo</span><span>Qta</span><span>Costo acquisto</span><span>Totale</span></div>{review.items.length ? review.items.map((item, index) => <div key={index} id={`ocr-row-${index}`} hidden={onlyPending && !rowIssues(index).length} className={`ocr-review-row${item.accepted ? "" : " is-discarded"}`}><div className="ocr-row-status"><strong>Riga {index + 1}</strong><span>{!item.accepted ? "Esclusa" : checking ? "Verifica…" : rowIssues(index).some((issue) => issue.kind === "conflict") ? "Da verificare" : rowIssues(index).length ? "Da completare" : "Pronta"}</span></div><div className="ocr-review-line"><label><input type="checkbox" checked={item.accepted} onChange={(event) => updateItem(index, "accepted", event.target.checked)} /><span className="sr-only">Includi articolo</span></label><input value={item.description} onChange={(event) => updateItem(index, "description", event.target.value)} /><select value={item.variant_id} onChange={(event) => updateItem(index, "variant_id", event.target.value)}><option value="">Seleziona articolo</option><option value="__new__">Crea articolo e variante</option>{variants.map((variant) => <option value={variant.id} key={variant.id}>{variant.product_name || "Articolo"} · {variant.sku}</option>)}</select><input inputMode="numeric" value={item.quantity} onChange={(event) => updateItem(index, "quantity", event.target.value)} /><input inputMode="decimal" value={item.unit_price} onChange={(event) => updateItem(index, "unit_price", event.target.value)} /><input readOnly value={money(lineTotal(item))} /></div>{item.variant_id && item.variant_id !== "__new__" && <label className="ocr-item-details">Prezzo vendita<input inputMode="decimal" value={item.sale_price} onChange={(event) => updateItem(index, "sale_price", event.target.value)} /></label>}{item.variant_id === "__new__" && <div className="ocr-new-variant"><label>Prodotto esistente<select value={item.new_variant.product_id} onChange={(event) => updateNewVariant(index, "product_id", event.target.value)}><option value="">Crea nuovo prodotto</option>{catalog.products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>{!item.new_variant.product_id && <><label>Nome nuovo prodotto<input value={item.new_variant.product_name} onChange={(event) => updateNewVariant(index, "product_name", event.target.value)} /></label><label>Categoria<span className="select-with-add"><select value={item.new_variant.category_id} onChange={(event) => updateNewVariant(index, "category_id", event.target.value)}><option value="">Seleziona</option>{catalog.categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select><button type="button" onClick={() => addCategory(index)} title="Aggiungi categoria"><Plus size={16} /></button></span></label><label>Aliquota IVA articolo<select value={item.new_variant.tax_rate_id || ""} onChange={(event) => updateNewVariant(index, "tax_rate_id", event.target.value)}><option value="">Seleziona aliquota</option>{catalog.taxes.map((tax) => <option key={tax.id} value={tax.id}>{tax.name}</option>)}</select></label></>}<label>Colore<span className="select-with-add"><select value={item.new_variant.color_id} onChange={(event) => updateNewVariant(index, "color_id", event.target.value)}><option value="">Nessuno</option>{catalog.colors.map((color) => <option key={color.id} value={color.id}>{color.name}</option>)}</select><button type="button" onClick={() => addColor(index)} title="Aggiungi colore"><Plus size={16} /></button></span></label><div className="ocr-variant-sizes"><div className="ocr-variant-sizes-heading"><strong>Taglie e quantità</strong><button type="button" onClick={() => addVariantSize(index)}><Plus size={15} /> Aggiungi taglia</button></div>{(item.new_variant.variants || []).map((variant, variantIndex) => <div className="ocr-variant-size-row" key={variantIndex}><label>Taglia<select value={variant.size_id} onChange={(event) => updateVariantDetail(index, variantIndex, "size_id", event.target.value)}><option value="">Seleziona</option>{catalog.sizes.map((size) => <option key={size.id} value={size.id}>{size.size_scale_name} · {size.label}</option>)}</select></label><label>Quantità<input inputMode="numeric" value={variant.quantity} onChange={(event) => updateVariantDetail(index, variantIndex, "quantity", event.target.value)} />{item.new_variant.variants.length === 1 && amount(variant.quantity) !== amount(item.quantity) && <button type="button" className="ocr-markup-action" onClick={() => updateVariantDetail(index, variantIndex, "quantity", item.quantity)}>Usa quantità riga: {item.quantity}</button>}</label><label>SKU<input value={variant.sku} onChange={(event) => updateVariantDetail(index, variantIndex, "sku", event.target.value)} /></label><label>Codice a barre<input value={variant.barcode || ""} onChange={(event) => updateVariantDetail(index, variantIndex, "barcode", event.target.value)} /></label><label>Prezzo vendita<input inputMode="decimal" value={variant.sale_price} onChange={(event) => updateVariantDetail(index, variantIndex, "sale_price", event.target.value)} /><button type="button" className="ocr-markup-action" onClick={() => updateVariantDetail(index, variantIndex, "sale_price", money(amount(item.unit_price) * amount(markup)))}>Applica ricarico</button></label><button type="button" className="ocr-remove-size" disabled={(item.new_variant.variants || []).length === 1} onClick={() => removeVariantSize(index, variantIndex)} title="Rimuovi taglia">×</button></div>)}</div></div>}{!checking && item.accepted && rowIssues(index).length > 0 && <div className="ocr-row-feedback">{[...new Set(rowIssues(index).map((issue) => issue.message.replace(/^Riga \d+:?\s*/, "")))].map((text) => <p key={text}>{text}</p>)}</div>}</div>) : <p className="ocr-review-empty">L’OCR non ha riconosciuto righe articolo in questo PDF.</p>}</div><div className="ocr-row-actions"><button type="button" className="secondary-action" onClick={() => changeReview((current) => ({ ...current, taxable_amount: money(reviewSubtotal), total_amount: money(reviewTotal) }))}>Ricalcola importi dalle righe</button><button type="button" className="secondary-action" onClick={() => updateReview("items", [...review.items, makeReview({ proposed_data: { items: [{}] } }).items[0]])}>Aggiungi riga</button></div></fieldset><div className="ocr-validation-summary" aria-live="polite">{imported ? <span>Proposta già caricata in magazzino.</span> : checking ? <span>Verifica in corso…</span> : conflicts.length ? <><span>{pendingRows.length > 0 ? `${pendingRows.length} righe da completare o verificare.` : "Completa i dati della fattura."} Puoi salvare la proposta in qualsiasi momento.</span><button type="button" onClick={goToPending}>Vai alla prima riga da controllare</button></> : <span>Tutto pronto per il carico in magazzino.</span>}</div><footer><p>Salva la proposta per riprenderla in seguito. La conferma crea fattura e ricezione e carica le quantità nella sede selezionata.</p><span><button type="button" className="secondary-action" disabled={reviewSaving || imported} onClick={saveDraft}>Salva proposta</button><button className="primary-action" disabled={reviewSaving || imported || checking || conflicts.length > 0} onClick={saveReview}>Conferma e carica in magazzino</button></span></footer></section></div>}
  </section>;
}
