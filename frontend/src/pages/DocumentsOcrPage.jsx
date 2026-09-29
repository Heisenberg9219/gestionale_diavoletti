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

function issueFields(issue) {
  const text = String(issue.message || "").toLocaleLowerCase("it-IT");
  if (text.includes("imponibile fattura deve coincidere")) return ["taxable_amount"];
  if (text.includes("numero fattura")) return ["invoice_number"];
  if (text.includes("fornitore")) return ["supplier_id"];
  if (text.includes("sede")) return ["location_id"];
  if (text.includes("data, imponibile, aliquota iva e totale")) return ["invoice_date", "taxable_amount", "tax_rate", "total_amount"];
  if (text.includes("nome e sku")) return ["product_name", "sku"];
  if (text.includes("nome identico") || text.includes("esiste già un articolo con nome") || text.includes("lunghezza massima")) return ["product_name"];
  if (text.includes("categoria")) return ["category_id"];
  if (text.includes("aliquota iva")) return ["tax_rate_id"];
  if (text.includes("colore")) return ["color_id"];
  if (text.includes("taglia")) return ["size_id"];
  if (text.includes("barcode")) return ["barcode"];
  if (text.includes("sku")) return ["sku"];
  if (text.includes("prezzo vendita")) return ["sale_price"];
  if (text.includes("costo acquisto")) return ["unit_price"];
  if (text.includes("includi almeno una riga")) return ["accepted"];
  if (text.includes("quantità") || text.includes("pezzi")) return ["quantity"];
  return ["variant_id"];
}

function FieldErrors({ issues }) {
  if (!issues.length) return null;
  return <span className="ocr-field-error" role="alert">{issues.map((issue) => issue.message).join(" ")}</span>;
}


function proposalLabel(analysis) {
  const status = analysis.proposed_data?.review?.status;
  const label = ["APPLIED", "IMPORTED"].includes(status) ? "Caricata in magazzino" : status ? "Bozza" : "Analisi OCR";
  const timestamp = new Date(analysis.created_at);
  const day = timestamp.toLocaleDateString("it-IT");
  const time = timestamp.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  return `${label} del ${day} alle ${time}`;
}

function latest(items, attachment) {
  return items.filter((item) => item.attachment === attachment && item.status === "SUCCEEDED").sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0];
}

function makeReview(analysis, catalog = { taxes: [] }, markup = "") {
  const proposal = analysis.proposed_data || {};
  const saved = proposal.review || {};
  const readOnly = ["IMPORTED", "APPLIED"].includes(saved.status);
  const defaultTax = readOnly ? null : catalog.taxes.find((tax) => tax.name?.toLowerCase().includes("ordinaria")) || catalog.taxes.find((tax) => tax.is_default);
  const defaultPrice = (cost) => !readOnly && amount(cost) > 0 && amount(markup) > 0 ? money(amount(cost) * amount(markup)) : "";
  return {
    ...saved,
    supplier_name: saved.supplier_name ?? proposal.supplier_name ?? "",
    invoice_number: saved.invoice_number ?? proposal.invoice_number ?? "",
    invoice_date: saved.invoice_date ?? proposal.invoice_date ?? "",
    supplier_id: saved.supplier_id ?? saved.supplier ?? "",
    location_id: saved.location_id ?? saved.location ?? "",
    taxable_amount: saved.taxable_amount ?? proposal.taxable_amount ?? "",
    tax_rate: saved.tax_rate !== undefined && saved.tax_rate !== "" ? saved.tax_rate : defaultTax?.percentage ?? "",
    total_amount: saved.total_amount ?? proposal.total_amount ?? "",
    items: (saved.items ?? proposal.items ?? []).map((row, index) => {
      const item = { ...(proposal.items?.[index] || {}), ...row };
      const previous = item.new_product || {};
      const stored = item.new_variant || {};
      return {
        ...item, accepted: item.accepted ?? true,
        variant_id: item.variant_id ?? ((item.new_product || item.new_variant) ? "__new__" : ""),
        description: item.description ?? "", quantity: item.quantity ?? "", unit_price: item.unit_price ?? "", sale_price: item.sale_price || defaultPrice(item.unit_price),
        new_variant: {
          product_id: previous.product_id || "", product_name: previous.name ?? item.description ?? "",
          category_id: previous.category || "", color_id: previous.color || "", ...stored,
          tax_rate_id: stored.tax_rate_id || previous.tax_rate || defaultTax?.id || "",
          variants: (stored.variants || [{ size_id: stored.size_id || previous.size || "", sku: stored.sku || previous.sku || "", barcode: stored.barcode || previous.barcode || "", quantity: item.quantity ?? "", sale_price: stored.sale_price ?? item.sale_price ?? "" }]).map((variant) => ({ ...variant, sale_price: variant.sale_price || defaultPrice(item.unit_price) })),
        },
      };
    }),
  };
}

export default function DocumentsOcrPage() {
  const [documents, setDocuments] = useState([]); const [types, setTypes] = useState([]); const [attachments, setAttachments] = useState([]); const [analyses, setAnalyses] = useState([]); const [variants, setVariants] = useState([]); const [suppliers, setSuppliers] = useState([]); const [locations, setLocations] = useState([]); const [catalog, setCatalog] = useState({ products: [], categories: [], taxes: [], colors: [], sizes: [] }); const [markup, setMarkup] = useState("");
  const [query, setQuery] = useState(""); const [formOpen, setFormOpen] = useState(false); const [form, setForm] = useState(blank()); const [saving, setSaving] = useState(false); const [message, setMessage] = useState(""); const [success, setSuccess] = useState(false);
  const [reviewAnalysis, setReviewAnalysis] = useState(null); const [review, setReview] = useState(null); const [reviewSaving, setReviewSaving] = useState(false); const [reviewError, setReviewError] = useState(""); const [reviewNotice, setReviewNotice] = useState(""); const [validationIssues, setValidationIssues] = useState([]);
  const proposalVersions = analyses
    .filter((entry) => entry.attachment === reviewAnalysis?.attachment && entry.status === "SUCCEEDED")
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  const imported = ["IMPORTED", "APPLIED"].includes(review?.status);
  const changeReview = (value) => setReview(value);
  const notice = (text, ok = true) => { setSuccess(ok); setMessage(text); };
  const load = async () => { try { const [a, b, c, d, e, f, g, h, i, j, k, l, m] = await Promise.all([allPages("/documents/documents/"), allPages("/documents/types/?is_active=True"), allPages("/documents/attachments/"), allPages("/documents/ocr-analyses/"), allPages("/catalog/variants/?page_size=200"), allPages("/suppliers/suppliers/?page_size=200"), allPages("/core/locations/?is_active=True"), allPages("/catalog/products/?is_active=True&page_size=200"), allPages("/catalog/categories/?is_active=True&page_size=200"), allPages("/core/tax-rates/?is_active=True&page_size=100"), allPages("/catalog/colors/?is_active=True&page_size=200"), allPages("/catalog/sizes/?is_active=True&page_size=200"), allPages("/core/settings/")]); setDocuments(list(a)); setTypes(list(b)); setAttachments(list(c)); setAnalyses(list(d)); setVariants(list(e)); setSuppliers(list(f)); setLocations(list(g)); setCatalog({ products: list(h), categories: list(i), taxes: list(j), colors: list(k), sizes: list(l) }); setMarkup(list(m)[0]?.default_markup || ""); } catch (error) { notice(error.message, false); } };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!message) return undefined; const timer = setTimeout(() => setMessage(""), 4000); return () => clearTimeout(timer); }, [message]);

  useEffect(() => {
    if (!reviewNotice) return undefined;
    const timer = setTimeout(() => setReviewNotice(""), 4000);
    return () => clearTimeout(timer);
  }, [reviewNotice]);

  const visible = useMemo(() => documents.filter((document) => `${document.title} ${document.number} ${document.counterparty_name}`.toLowerCase().includes(query.toLowerCase())), [documents, query]);
  const typeFor = (id) => types.find((item) => item.id === id);
  const attachmentFor = (documentId) => attachments.filter((item) => item.document === documentId).sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0];
  const analysisForDocument = (documentId) => analyses
    .filter((analysis) => attachments.some((attachment) => attachment.id === analysis.attachment && attachment.document === documentId))
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0];
  const closeReview = () => { if (reviewSaving) return; setReviewAnalysis(null); setReview(null); setReviewError(""); setReviewNotice(""); setValidationIssues([]); };
  const fieldIssues = (row, field) => validationIssues.filter((issue) => (issue.row ?? null) === row && issueFields(issue).includes(field));
  const updateReview = (key, value) => { setValidationIssues((current) => current.filter((issue) => !((issue.row ?? null) === null && issueFields(issue).includes(key)))); changeReview((current) => ({ ...current, [key]: value })); };
  const updateItem = (index, key, value) => { setValidationIssues((current) => current.filter((issue) => !((issue.row ?? null) === index && issueFields(issue).includes(key)))); changeReview((current) => ({ ...current, items: current.items.map((item, itemIndex) => {
    if (itemIndex !== index) return item;
    const updated = { ...item, [key]: value };
    if (key === "quantity" && item.new_variant.variants.length === 1) {
      updated.new_variant = { ...item.new_variant, variants: [{ ...item.new_variant.variants[0], quantity: value }] };
    }
    if (key === "unit_price" && amount(markup) > 0) {
      const previousPrice = money(amount(item.unit_price) * amount(markup));
      const nextPrice = amount(value) > 0 ? money(amount(value) * amount(markup)) : "";
      updated.sale_price = !item.sale_price || money(item.sale_price) === previousPrice ? nextPrice : item.sale_price;
      updated.new_variant = { ...item.new_variant, variants: item.new_variant.variants.map((variant) => ({ ...variant,
        sale_price: !variant.sale_price || money(variant.sale_price) === previousPrice ? nextPrice : variant.sale_price,
      })) };
    }
    return updated;
  }) })); };
  const updateNewVariant = (index, key, value) => { setValidationIssues((current) => current.filter((issue) => !((issue.row ?? null) === index && issueFields(issue).includes(key)))); changeReview((current) => ({ ...current, items: current.items.map((item, itemIndex) => itemIndex === index ? { ...item, new_variant: { ...item.new_variant, [key]: value } } : item) })); };
  const updateVariantDetail = (itemIndex, variantIndex, key, value) => { setValidationIssues((current) => current.filter((issue) => !((issue.row ?? null) === itemIndex && issueFields(issue).includes(key)))); changeReview((current) => ({ ...current, items: current.items.map((item, index) => index === itemIndex ? { ...item, new_variant: { ...item.new_variant, variants: (item.new_variant.variants || []).map((variant, variantPosition) => variantPosition === variantIndex ? { ...variant, [key]: value } : variant) } } : item) })); };
  const removeReviewItem = (itemIndex) => { setValidationIssues((current) => current.filter((issue) => (issue.row ?? null) !== itemIndex)); changeReview((current) => ({ ...current, items: current.items.filter((_, index) => index !== itemIndex) })); };
  const addVariantSize = (itemIndex) => changeReview((current) => ({ ...current, items: current.items.map((item, index) => index === itemIndex ? { ...item, new_variant: { ...item.new_variant, variants: [...(item.new_variant.variants || []), { size_id: "", sku: "", barcode: "", quantity: "", sale_price: amount(item.unit_price) > 0 && amount(markup) > 0 ? money(amount(item.unit_price) * amount(markup)) : "" }] } } : item) }));
  const removeVariantSize = (itemIndex, variantIndex) => changeReview((current) => ({ ...current, items: current.items.map((item, index) => index === itemIndex ? { ...item, new_variant: { ...item.new_variant, variants: item.new_variant.variants.filter((_, position) => position !== variantIndex) } } : item) }));
  async function addCategory(itemIndex) { const name = window.prompt("Nome della nuova categoria")?.trim(); if (!name) return; const code = `${name.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 20) || "CATEGORIA"}_${Date.now().toString().slice(-5)}`; try { const category = await request("/catalog/categories/", { method: "POST", body: JSON.stringify({ code, name }) }); setCatalog((current) => ({ ...current, categories: [...current.categories, category] })); updateNewVariant(itemIndex, "category_id", category.id); } catch (error) { setReviewError(error.message); } }
  async function addColor(itemIndex) { const name = window.prompt("Nome del nuovo colore")?.trim(); if (!name) return; const code = `${name.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 20) || "COLORE"}_${Date.now().toString().slice(-5)}`; try { const color = await request("/catalog/colors/", { method: "POST", body: JSON.stringify({ code, name }) }); setCatalog((current) => ({ ...current, colors: [...current.colors, color] })); updateNewVariant(itemIndex, "color_id", color.id); } catch (error) { setReviewError(error.message); } }
  const reviewSubtotal = review?.items.filter((item) => item.accepted).reduce((total, item) => total + lineTotal(item), 0) || 0;
  const reviewTax = reviewSubtotal * amount(review?.tax_rate) / 100;
  const reviewTotal = reviewSubtotal + reviewTax;
  const recalculateAmounts = () => {
    setValidationIssues((current) => current.filter((issue) => !((issue.row ?? null) === null && ["taxable_amount", "total_amount"].some((field) => issueFields(issue).includes(field)))));
    changeReview((current) => {
      const taxable = current.items.filter((item) => item.accepted).reduce((total, item) => total + lineTotal(item), 0);
      const total = taxable + taxable * amount(current.tax_rate) / 100;
      return { ...current, taxable_amount: money(taxable), total_amount: money(total) };
    });
  };

  async function upload(event) { event.preventDefault(); if (!form.file) return notice("Seleziona un PDF da allegare.", false); setSaving(true); try { const type = typeFor(form.document_type); const document = await request("/documents/documents/", { method: "POST", body: JSON.stringify({ document_type: form.document_type, direction: type.direction, status: "DRAFT", number: form.number, document_date: form.document_date, title: form.title, taxable_amount: "0.00", tax_amount: "0.00", total_amount: "0.00", counterparty_name: form.counterparty_name }) }); const data = new FormData(); data.append("file", form.file); data.append("description", "Documento caricato per analisi OCR"); await request(`/documents/documents/${document.id}/upload-attachment/`, { method: "POST", body: data }); setFormOpen(false); setForm(blank()); notice("Documento e PDF caricati. Avvia l'OCR per preparare la proposta."); await load(); } catch (error) { notice(error.message, false); } finally { setSaving(false); } }
  async function analyze(attachment) { try { await request(`/documents/attachments/${attachment.id}/analyze-invoice/`, { method: "POST", body: JSON.stringify({}) }); notice("Analisi OCR completata. Apri la proposta per controllare gli articoli."); await load(); } catch (error) { notice(error.message, false); await load(); } }
  async function finalize(document) { try { await request(`/documents/documents/${document.id}/finalize/`, { method: "POST", body: JSON.stringify({ number: document.number }) }); notice("Documento registrato correttamente."); await load(); } catch (error) { notice(error.message, false); } }
  const draftReview = () => ({ ...review, supplier: review.supplier_id, location: review.location_id });
  const applyReview = () => ({ ...draftReview(), items: review.items.map((item) => ({ ...item, variant_id: item.variant_id === "__new__" ? "" : item.variant_id, new_variant: item.variant_id === "__new__" ? item.new_variant : undefined })) });
  async function saveDraft() {
    setReviewSaving(true); setReviewError(""); setReviewNotice("");
    try {
      const saved = await request(`/documents/ocr-analyses/${reviewAnalysis.id}/save-purchase-proposal/`, { method: "POST", body: JSON.stringify({ review: draftReview() }) });
      setReviewAnalysis(saved); changeReview(makeReview(saved, catalog, markup));
      setReviewNotice("Proposta salvata. Le giacenze non sono state modificate."); await load();
    } catch (error) { setReviewError(`La bozza non è stata salvata: ${error.message}`); } finally { setReviewSaving(false); }
  }
  async function saveReview() {
    setReviewSaving(true); setReviewError(""); setReviewNotice(""); setValidationIssues([]);
    try {
      const proposal = applyReview();
      const validation = await request(`/documents/attachments/${reviewAnalysis.attachment}/validate-review/`, { method: "POST", body: JSON.stringify({ review: proposal }) });
      if (validation.conflicts.length) {
        const issues = validation.issues?.length ? validation.issues : validation.conflicts.map((message) => ({ row: null, kind: "incomplete", message }));
        setValidationIssues(issues);
        window.setTimeout(() => document.querySelector(".ocr-field-error")?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
        return;
      }
      await request(`/documents/ocr-analyses/${reviewAnalysis.id}/save-purchase-proposal/`, { method: "POST", body: JSON.stringify({ review: draftReview() }) });
      await request(`/documents/ocr-analyses/${reviewAnalysis.id}/apply-purchase-proposal/`, { method: "POST", body: JSON.stringify({ review: proposal, supplier: review.supplier_id, location: review.location_id }) });
      setReviewAnalysis(null); setReview(null); notice("Fattura registrata, Catalogo e Magazzino aggiornati."); await load();
    } catch (error) { setReviewError(`Il carico non è stato registrato: ${error.message}`); } finally { setReviewSaving(false); }
  }

  return <section className="products-page documents-page">
    <div className="page-title-row"><div><p className="eyebrow">Gestione</p><h2>Documenti e OCR</h2><span>Carica fatture e documenti PDF, poi verifica gli articoli rilevati.</span></div><button className="primary-action" onClick={() => { setForm(blank()); setFormOpen(true); }}><Plus size={17} /> Carica documento</button></div>
    {formOpen && <form className="document-form" onSubmit={upload}><div className="inventory-form-copy document-copy"><p className="eyebrow">Nuovo documento</p><h3>Carica un PDF</h3><span>L'OCR riconosce i dati della fattura dopo il caricamento.</span></div><label>Tipo documento<select required value={form.document_type} onChange={(event) => setForm({ ...form, document_type: event.target.value })}><option value="">Seleziona tipo</option>{types.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Titolo<input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label><label>Numero documento<input value={form.number} onChange={(event) => setForm({ ...form, number: event.target.value })} /></label><label>Data documento<input required type="date" value={form.document_date} onChange={(event) => setForm({ ...form, document_date: event.target.value })} /></label><label>Fornitore<input value={form.counterparty_name} onChange={(event) => setForm({ ...form, counterparty_name: event.target.value })} /></label><label>File PDF<span className="document-file-control"><input id="document-pdf" required type="file" accept="application/pdf" onChange={(event) => setForm({ ...form, file: event.target.files?.[0] || null })} /><button type="button" onClick={() => document.getElementById("document-pdf")?.click()}>Scegli file</button><span>{form.file?.name || "Nessun file selezionato"}</span></span></label><div className="inline-form-actions"><button type="button" className="secondary-action" onClick={() => setFormOpen(false)}>Annulla</button><button className="primary-action" disabled={saving}>{saving ? "Caricamento..." : "Carica"}</button></div></form>}
    {message && <p className={success ? "operation-success" : "catalog-error"}>{message}</p>}
    <div className="voucher-filters"><div className="products-search"><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Cerca documento, numero o fornitore" /></div></div>
    <article className="products-list"><div className="document-heading"><span>Documento</span><span>Tipo</span><span>Data</span><span>PDF e OCR</span><span>Stato</span><span>Azioni</span></div>{!visible.length ? <div className="empty-product-state"><FileText size={28} /><strong>Nessun documento trovato</strong><span>Carica un PDF per costruire l'archivio documentale.</span></div> : visible.map((document) => { const analysis = analysisForDocument(document.id); const attachment = attachments.find((item) => item.id === analysis?.attachment) || attachmentFor(document.id); const reviewed = Boolean(analysis?.proposed_data?.review?.status); return <div className="document-row" key={document.id}><div><strong>{document.title}</strong><span>{document.number || "Numero non indicato"}{document.counterparty_name ? ` · ${document.counterparty_name}` : ""}</span></div><span>{typeFor(document.document_type)?.name || directionLabel[document.direction]}</span><span>{date(document.document_date)}</span><span>{analysis?.status === "SUCCEEDED" ? reviewed ? ["APPLIED", "IMPORTED"].includes(analysis.proposed_data.review.status) ? "Caricato in magazzino" : "Proposta salvata" : "OCR completato" : analysis?.status === "FAILED" ? "OCR non disponibile" : attachment ? "PDF pronto" : "Nessun PDF"}</span><em className={`document-status ${document.status.toLowerCase()}`}>{statusLabel[document.status] || document.status}</em><div className="document-actions">{analysis?.status === "SUCCEEDED" && <button title="Apri proposta OCR" onClick={() => { setReviewAnalysis(analysis); setReviewError(""); setReviewNotice(""); setValidationIssues([]); changeReview(makeReview(analysis, catalog, markup)); }}><Eye size={16} /></button>}{attachment && <button title="Analizza fattura con OCR" onClick={() => analyze(attachment)}><ScanText size={16} /></button>}{document.status === "DRAFT" && reviewed && <button title="Registra documento" onClick={() => finalize(document)}><CheckCircle2 size={16} /></button>}{attachment?.file && <a href={attachment.file} target="_blank" rel="noreferrer" title="Apri PDF"><FileUp size={16} /></a>}</div></div>; })}</article>
    {reviewAnalysis && review && <div className="ocr-review-layer" role="dialog" aria-modal="true">
      <button className="ocr-review-backdrop" aria-label="Chiudi" onClick={closeReview} />
      <section className="ocr-review-modal">
        <header><div><p className="eyebrow">Proposta OCR</p><h3>Controlla e registra la fattura</h3></div><button type="button" title="Chiudi" onClick={closeReview}><X size={20} /></button></header>
        {reviewError && <p className="ocr-review-feedback error" role="alert">{reviewError}</p>}
        {reviewNotice && <p className="ocr-review-feedback success">{reviewNotice}</p>}
        {proposalVersions.length > 1 && <div className="ocr-proposal-history"><label htmlFor="ocr-proposal-version">Versione della proposta</label><select id="ocr-proposal-version" disabled={reviewSaving} value={reviewAnalysis.id} onChange={(event) => { const selected = proposalVersions.find((entry) => entry.id === event.target.value); setReviewError(""); setReviewNotice(""); setValidationIssues([]); setReviewAnalysis(selected); changeReview(makeReview(selected, catalog, markup)); }}>{proposalVersions.map((entry) => <option key={entry.id} value={entry.id}>{proposalLabel(entry)}</option>)}</select></div>}
        <fieldset className="ocr-review-fields" disabled={reviewSaving || imported}>
          <div id="ocr-invoice-fields" className="ocr-review-summary">
            <label>Fornitore<input value={review.supplier_name} onChange={(event) => updateReview("supplier_name", event.target.value)} /></label>
            <label className={fieldIssues(null, "supplier_id").length ? "ocr-invalid" : ""}>Fornitore in rubrica<select value={review.supplier_id} onChange={(event) => updateReview("supplier_id", event.target.value)}><option value="">Seleziona fornitore</option>{suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.business_name}</option>)}</select><FieldErrors issues={fieldIssues(null, "supplier_id")} /></label>
            <label className={fieldIssues(null, "location_id").length ? "ocr-invalid" : ""}>Destinazione carico<select value={review.location_id} onChange={(event) => updateReview("location_id", event.target.value)}><option value="">Seleziona sede</option>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select><FieldErrors issues={fieldIssues(null, "location_id")} /></label>
            <label className={fieldIssues(null, "invoice_number").length ? "ocr-invalid" : ""}>Numero fattura<input value={review.invoice_number} onChange={(event) => updateReview("invoice_number", event.target.value)} /><FieldErrors issues={fieldIssues(null, "invoice_number")} /></label>
            <label className={fieldIssues(null, "invoice_date").length ? "ocr-invalid" : ""}>Data<input type="date" value={review.invoice_date} onChange={(event) => updateReview("invoice_date", event.target.value)} /><FieldErrors issues={fieldIssues(null, "invoice_date")} /></label>
            <label className={fieldIssues(null, "taxable_amount").length ? "ocr-invalid" : ""}>Imponibile articoli<input inputMode="decimal" value={review.taxable_amount} onChange={(event) => updateReview("taxable_amount", event.target.value)} /><FieldErrors issues={fieldIssues(null, "taxable_amount")} /></label>
            <label className={fieldIssues(null, "tax_rate").length ? "ocr-invalid" : ""}>IVA %<input inputMode="decimal" value={review.tax_rate} onChange={(event) => updateReview("tax_rate", event.target.value)} /><FieldErrors issues={fieldIssues(null, "tax_rate")} /></label>
            <label className={fieldIssues(null, "total_amount").length ? "ocr-invalid" : ""}>Totale fattura<input inputMode="decimal" value={review.total_amount} onChange={(event) => updateReview("total_amount", event.target.value)} /><FieldErrors issues={fieldIssues(null, "total_amount")} /></label>
          </div>
          <div className="ocr-review-lines"><div className="ocr-review-heading"><span>Incl.</span><span>Descrizione</span><span>Articolo in catalogo</span><span>Qta</span><span>Costo acquisto</span><span>Totale</span><span /></div>
          {review.items.length ? review.items.map((item, index) => <div key={index} id={`ocr-row-${index}`} className={`ocr-review-row${item.accepted ? "" : " is-discarded"}`}>
            <div className="ocr-review-line">
              <span className={fieldIssues(index, "accepted").length ? "ocr-inclusion ocr-invalid" : "ocr-inclusion"}><label><input type="checkbox" checked={item.accepted} onChange={(event) => updateItem(index, "accepted", event.target.checked)} /><span className="sr-only">Includi articolo</span></label><FieldErrors issues={fieldIssues(index, "accepted")} /></span>
              <input value={item.description} onChange={(event) => updateItem(index, "description", event.target.value)} />
              <span className={fieldIssues(index, "variant_id").length ? "ocr-control ocr-invalid" : "ocr-control"}><select value={item.variant_id} onChange={(event) => updateItem(index, "variant_id", event.target.value)}><option value="">Seleziona articolo</option><option value="__new__">Crea articolo e variante</option>{variants.map((variant) => <option value={variant.id} key={variant.id}>{variant.product_name || "Articolo"} · {variant.sku}</option>)}</select><FieldErrors issues={fieldIssues(index, "variant_id")} /></span>
              <span className={fieldIssues(index, "quantity").length ? "ocr-control ocr-invalid" : "ocr-control"}><input inputMode="numeric" value={item.quantity} onChange={(event) => updateItem(index, "quantity", event.target.value)} /><FieldErrors issues={fieldIssues(index, "quantity")} /></span>
              <span className={fieldIssues(index, "unit_price").length ? "ocr-control ocr-invalid" : "ocr-control"}><input inputMode="decimal" value={item.unit_price} onChange={(event) => updateItem(index, "unit_price", event.target.value)} /><FieldErrors issues={fieldIssues(index, "unit_price")} /></span>
              <input readOnly value={money(lineTotal(item))} />
              <button type="button" className="ocr-remove-row" onClick={() => removeReviewItem(index)} title="Elimina riga">×</button>
            </div>
            {item.variant_id && item.variant_id !== "__new__" && <label className={`ocr-item-details${fieldIssues(index, "sale_price").length ? " ocr-invalid" : ""}`}>Prezzo vendita<input inputMode="decimal" value={item.sale_price} onChange={(event) => updateItem(index, "sale_price", event.target.value)} /><FieldErrors issues={fieldIssues(index, "sale_price")} /></label>}
            {item.variant_id === "__new__" && <div className="ocr-new-variant">
              <label>Prodotto esistente<select value={item.new_variant.product_id} onChange={(event) => updateNewVariant(index, "product_id", event.target.value)}><option value="">Crea nuovo prodotto</option>{catalog.products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>
              {!item.new_variant.product_id && <><label className={fieldIssues(index, "product_name").length ? "ocr-invalid" : ""}>Nome nuovo prodotto<input value={item.new_variant.product_name} onChange={(event) => updateNewVariant(index, "product_name", event.target.value)} /><FieldErrors issues={fieldIssues(index, "product_name")} /></label><label className={fieldIssues(index, "category_id").length ? "ocr-invalid" : ""}>Categoria<span className="select-with-add"><select value={item.new_variant.category_id} onChange={(event) => updateNewVariant(index, "category_id", event.target.value)}><option value="">Seleziona</option>{catalog.categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select><button type="button" onClick={() => addCategory(index)} title="Aggiungi categoria"><Plus size={16} /></button></span><FieldErrors issues={fieldIssues(index, "category_id")} /></label><label className={fieldIssues(index, "tax_rate_id").length ? "ocr-invalid" : ""}>Aliquota IVA articolo<select value={item.new_variant.tax_rate_id || ""} onChange={(event) => updateNewVariant(index, "tax_rate_id", event.target.value)}><option value="">Seleziona aliquota</option>{catalog.taxes.map((tax) => <option key={tax.id} value={tax.id}>{tax.name}</option>)}</select><FieldErrors issues={fieldIssues(index, "tax_rate_id")} /></label></>}
              <label className={fieldIssues(index, "color_id").length ? "ocr-invalid" : ""}>Colore<span className="select-with-add"><select value={item.new_variant.color_id} onChange={(event) => updateNewVariant(index, "color_id", event.target.value)}><option value="">Nessuno</option>{catalog.colors.map((color) => <option key={color.id} value={color.id}>{color.name}</option>)}</select><button type="button" onClick={() => addColor(index)} title="Aggiungi colore"><Plus size={16} /></button></span><FieldErrors issues={fieldIssues(index, "color_id")} /></label>
              <div className="ocr-variant-sizes"><div className="ocr-variant-sizes-heading"><strong>Taglie e quantità</strong><button type="button" onClick={() => addVariantSize(index)}><Plus size={15} /> Aggiungi taglia</button></div>{(item.new_variant.variants || []).map((variant, variantIndex) => <div className="ocr-variant-size-row" key={variantIndex}>
                <label className={fieldIssues(index, "size_id").length ? "ocr-invalid" : ""}>Taglia<select value={variant.size_id} onChange={(event) => updateVariantDetail(index, variantIndex, "size_id", event.target.value)}><option value="">Seleziona</option>{catalog.sizes.map((size) => <option key={size.id} value={size.id}>{size.size_scale_name} · {size.label}</option>)}</select><FieldErrors issues={fieldIssues(index, "size_id")} /></label>
                <label className={fieldIssues(index, "quantity").length ? "ocr-invalid" : ""}>Quantità<input inputMode="numeric" value={variant.quantity} onChange={(event) => updateVariantDetail(index, variantIndex, "quantity", event.target.value)} />{item.new_variant.variants.length === 1 && amount(variant.quantity) !== amount(item.quantity) && <button type="button" className="ocr-markup-action" onClick={() => updateVariantDetail(index, variantIndex, "quantity", item.quantity)}>Usa quantità riga: {item.quantity}</button>}<FieldErrors issues={fieldIssues(index, "quantity")} /></label>
                <label className={fieldIssues(index, "sku").length ? "ocr-invalid" : ""}>SKU<input value={variant.sku} onChange={(event) => updateVariantDetail(index, variantIndex, "sku", event.target.value)} /><FieldErrors issues={fieldIssues(index, "sku")} /></label>
                <label className={fieldIssues(index, "barcode").length ? "ocr-invalid" : ""}>Codice a barre<input value={variant.barcode || ""} onChange={(event) => updateVariantDetail(index, variantIndex, "barcode", event.target.value)} /><FieldErrors issues={fieldIssues(index, "barcode")} /></label>
                <label className={fieldIssues(index, "sale_price").length ? "ocr-invalid" : ""}>Prezzo vendita<input inputMode="decimal" value={variant.sale_price} onChange={(event) => updateVariantDetail(index, variantIndex, "sale_price", event.target.value)} /><button type="button" className="ocr-markup-action" onClick={() => updateVariantDetail(index, variantIndex, "sale_price", money(amount(item.unit_price) * amount(markup)))}>Applica ricarico</button><FieldErrors issues={fieldIssues(index, "sale_price")} /></label>
                <button type="button" className="ocr-remove-size" disabled={(item.new_variant.variants || []).length === 1} onClick={() => removeVariantSize(index, variantIndex)} title="Rimuovi taglia">×</button>
              </div>)}</div>
            </div>}
          </div>) : <p className="ocr-review-empty">L’OCR non ha riconosciuto righe articolo in questo PDF.</p>}</div>
          <div className="ocr-row-actions"><button type="button" className="secondary-action" onClick={recalculateAmounts}>Ricalcola importi dalle righe incluse</button><button type="button" className="secondary-action" onClick={() => updateReview("items", [...review.items, makeReview({ proposed_data: { items: [{}] } }, catalog, markup).items[0]])}>Aggiungi riga</button></div>
        </fieldset>
        <footer><span><button type="button" className="secondary-action" disabled={reviewSaving || imported} onClick={saveDraft}>Salva proposta</button><button className="primary-action" disabled={reviewSaving || imported} onClick={saveReview}>Conferma e carica in magazzino</button></span></footer>
      </section>
    </div>}
  </section>;
}
