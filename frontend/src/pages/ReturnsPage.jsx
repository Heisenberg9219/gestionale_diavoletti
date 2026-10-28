import { useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, PackageSearch, RefreshCcw, Search, Ticket, XCircle } from "lucide-react";
import { request } from "../api";
import PaginatedRows from "../components/PaginatedRows";
import "../returns.css";

const euro = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
const list = (payload) => payload?.results || payload || [];
const dateFormat = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short", year: "numeric" });
const dateTimeFormat = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
const STATUS_LABELS = { CONFIRMED: "Confermato", CANCELLED: "Annullato", DRAFT: "Bozza" };
const VOUCHER_STATUS = { ACTIVE: "Attivo", EXHAUSTED: "Esaurito", CANCELLED: "Annullato" };

// Taglia, colore e codice di una riga di vendita, nell'ordine in cui servono al banco.
function lineDetails(line) {
  return [
    line?.size_snapshot && `Taglia ${line.size_snapshot}`,
    line?.color_snapshot && `Colore ${line.color_snapshot}`,
    line?.sku_snapshot && `Cod. ${line.sku_snapshot}`,
  ].filter(Boolean).join(" · ");
}

export default function ReturnsPage({ canCancelConfirmed = false, onNavigate, onStartExchange, initialSale, onClearInitialSale }) {
  const [returns, setReturns] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  // Nuovo reso
  const [wizard, setWizard] = useState(false);
  const [saleQuery, setSaleQuery] = useState("");
  const [sales, setSales] = useState([]);
  const [selectedSale, setSelectedSale] = useState(null);
  const [returnable, setReturnable] = useState({});
  const [selectedLines, setSelectedLines] = useState({});
  const [reason, setReason] = useState("Reso cliente");
  const [saving, setSaving] = useState(false);
  const [completed, setCompleted] = useState(null);
  // Dettaglio di un reso esistente
  const [detail, setDetail] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [detailBusy, setDetailBusy] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");

  const loadReturns = () => {
    setLoading(true);
    request(`/returns/returns/?search=${encodeURIComponent(search)}&page_size=200&ordering=-created_at`)
      .then((payload) => { setReturns(list(payload)); setError(""); })
      .catch(() => setError("Non è stato possibile caricare lo storico resi."))
      .finally(() => setLoading(false));
  };
  useEffect(loadReturns, []);

  useEffect(() => {
    if (!initialSale) return;
    selectSale(initialSale);
    setWizard(true);
    onClearInitialSale?.();
  }, [initialSale, onClearInitialSale]);

  // ---------- Nuovo reso ----------

  async function findSales(event) {
    event?.preventDefault();
    if (!saleQuery.trim()) return;
    setError("");
    try {
      setSales(list(await request(`/sales/sales/?status=CONFIRMED&search=${encodeURIComponent(saleQuery.trim())}`)));
    } catch {
      setError("Ricerca vendite non disponibile.");
    }
  }

  // Per ogni riga chiede al server quanti pezzi si possono ancora restituire,
  // così gli articoli già resi non si possono selezionare una seconda volta.
  async function selectSale(sale) {
    setSelectedSale(sale);
    setSelectedLines({});
    setSales([]);
    setReturnable({});
    const entries = await Promise.all((sale.lines || []).map(async (line) => {
      try {
        const result = await request(`/sales/lines/${line.id}/returnable-quantity/`);
        return [line.id, Number(result.quantity)];
      } catch {
        return [line.id, Number(line.quantity)];
      }
    }));
    setReturnable(Object.fromEntries(entries));
  }

  function setLine(line, checked) {
    setSelectedLines((current) => ({ ...current, [line.id]: checked ? { quantity: 1, restock: true } : undefined }));
  }

  function setLineQuantity(line, quantity) {
    setSelectedLines((current) => ({ ...current, [line.id]: { ...current[line.id], quantity } }));
  }

  async function voucherCredit(confirmed) {
    const voucher = confirmed.return_voucher
      ? await request(`/vouchers/vouchers/${confirmed.return_voucher}/`).catch(() => null)
      : null;
    return { voucherId: confirmed.return_voucher, code: voucher?.code || "", amount: Number(confirmed.total_refund_amount), returnNumber: confirmed.number };
  }

  async function confirmReturn(mode = "voucher") {
    const lines = Object.entries(selectedLines).filter(([, value]) => value);
    if (!lines.length) return setError("Seleziona almeno un articolo da restituire.");
    if (!reason.trim()) return setError("Inserisci il motivo del reso.");
    setSaving(true);
    setError("");
    let draft = null;
    try {
      draft = await request("/returns/returns/create-draft/", { method: "POST", body: JSON.stringify({ original_sale: selectedSale.id, reason }) });
      for (const [line, value] of lines) {
        await request(`/returns/returns/${draft.id}/set-line/`, { method: "POST", body: JSON.stringify({ original_sale_line: line, quantity: value.quantity, restock: value.restock }) });
      }
      const confirmed = await request(`/returns/returns/${draft.id}/confirm/`, { method: "POST" });
      draft = null;
      const credit = await voucherCredit(confirmed);
      if (mode === "exchange" && credit.code && onStartExchange) {
        resetWizard();
        onStartExchange(credit);
        return;
      }
      setCompleted({ ...confirmed, voucher_code: credit.code, credit });
      loadReturns();
    } catch (err) {
      // Se qualcosa va storto a metà, la bozza appena creata viene annullata
      // per non lasciare resi incompleti nello storico.
      if (draft) {
        await request(`/returns/returns/${draft.id}/cancel/`, { method: "POST", body: JSON.stringify({ reason: `Annullato automaticamente: ${err.message}`.slice(0, 250) }) }).catch(() => {});
      }
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  function resetWizard() {
    setWizard(false);
    setSaleQuery("");
    setSales([]);
    setSelectedSale(null);
    setSelectedLines({});
    setReturnable({});
    setCompleted(null);
    setReason("Reso cliente");
    setError("");
  }

  // ---------- Dettaglio ----------

  async function openDetail(item) {
    setDetail(item);
    setDetailData(null);
    setDetailError("");
    setDetailLoading(true);
    try {
      const [sale, lines, voucher] = await Promise.all([
        request(`/sales/sales/${item.original_sale}/`).catch(() => null),
        request(`/returns/lines/?customer_return=${item.id}&page_size=200`).then(list),
        item.return_voucher ? request(`/vouchers/vouchers/${item.return_voucher}/`).catch(() => null) : null,
      ]);
      setDetailData({ sale, lines, voucher });
    } catch (err) {
      setDetailError(err.message || "Impossibile caricare il dettaglio del reso.");
    } finally {
      setDetailLoading(false);
    }
  }

  function closeDetail() {
    setCancelOpen(false);
    setCancelReason("");
    setDetail(null);
    setDetailData(null);
    setDetailError("");
  }

  async function confirmDraft() {
    setDetailBusy(true);
    setDetailError("");
    try {
      const confirmed = await request(`/returns/returns/${detail.id}/confirm/`, { method: "POST" });
      loadReturns();
      await openDetail(confirmed);
    } catch (err) {
      setDetailError(err.message);
    } finally {
      setDetailBusy(false);
    }
  }

  async function cancelDraft() {
    setDetailBusy(true);
    setDetailError("");
    try {
      const cancelled = await request(`/returns/returns/${detail.id}/cancel/`, { method: "POST", body: JSON.stringify({ reason: "Bozza annullata dal negozio" }) });
      loadReturns();
      await openDetail(cancelled);
    } catch (err) {
      setDetailError(err.message);
    } finally {
      setDetailBusy(false);
    }
  }

  // Annulla un reso confermato: il capo esce di nuovo dal magazzino, il buono
  // viene annullato e i punti tornano al cliente. Il server lo consente solo
  // al titolare e solo se il buono non è stato usato.
  async function cancelConfirmed(event) {
    event.preventDefault();
    if (!cancelReason.trim()) return setDetailError("Scrivi il motivo dell'annullamento.");
    setDetailBusy(true);
    setDetailError("");
    try {
      const cancelled = await request(`/returns/returns/${detail.id}/cancel/`, { method: "POST", body: JSON.stringify({ reason: cancelReason.trim() }) });
      setCancelOpen(false);
      setCancelReason("");
      loadReturns();
      await openDetail(cancelled);
    } catch (err) {
      setDetailError(err.message);
    } finally {
      setDetailBusy(false);
    }
  }

  // ---------- Schermate ----------

  if (detail) {
    const saleLines = Object.fromEntries((detailData?.sale?.lines || []).map((line) => [line.id, line]));
    const lines = detailData?.lines || [];
    const voucher = detailData?.voucher;
    const draftTotal = lines.reduce((total, line) => total + Number(line.total_refund_amount || 0), 0);
    const total = detail.confirmed_at ? Number(detail.total_refund_amount) : draftTotal;
    const voucherUnused = voucher && voucher.status === "ACTIVE" && Number(voucher.current_balance) === Number(voucher.initial_amount);
    const voucherBlock = (detail.status === "CONFIRMED" || (detail.status === "CANCELLED" && detail.confirmed_at));
    return (
      <section className="returns-page return-detail">
        <div className="page-title-row">
          <div>
            <p className="eyebrow">Operatività · Resi</p>
            <h2>{detail.number || "Reso in bozza"}</h2>
            <span>
              {detailData?.sale ? `Scontrino ${detailData.sale.number}` : "Scontrino collegato"} · creato il {dateTimeFormat.format(new Date(detail.created_at))}
            </span>
          </div>
          <button className="secondary-action return-back" onClick={closeDetail}><ArrowLeft size={17} /> Torna allo storico</button>
        </div>
        <section className="return-lines-card">
          <div className="return-detail-summary">
            <div><span>Stato</span><strong className={`return-status ${detail.status.toLowerCase()}`}>{STATUS_LABELS[detail.status]}</strong></div>
            <div><span>Motivo</span><strong>{detail.reason || "—"}</strong></div>
            <div><span>Valore reso</span><strong>{euro.format(total)}</strong></div>
            {detail.confirmed_at && <div><span>Confermato il</span><strong>{dateTimeFormat.format(new Date(detail.confirmed_at))}</strong></div>}
            {detail.cancelled_at && <div><span>Annullato il</span><strong>{dateTimeFormat.format(new Date(detail.cancelled_at))}</strong></div>}
          </div>
          {detail.cancellation_reason && <p className="return-detail-note">Motivo annullamento: {detail.cancellation_reason}</p>}
          {detailLoading && <p className="return-detail-note">Caricamento dettaglio...</p>}
          {!detailLoading && (
            <>
              <h3 className="return-detail-title">Articoli restituiti</h3>
              {!lines.length && <p className="return-detail-note">Nessun articolo registrato in questo reso.</p>}
              <div className="return-lines">
                {lines.map((line) => (
                  <div className="return-line" key={line.id}>
                    <div>
                      <strong>{line.product_name_snapshot}</strong>
                      <span>{lineDetails({ ...saleLines[line.original_sale_line], sku_snapshot: line.sku_snapshot })}</span>
                      <span>Quantità resa: {line.quantity}{line.restock ? " · rientrato in magazzino" : ""}</span>
                    </div>
                    <b>{euro.format(Number(line.total_refund_amount))}</b>
                  </div>
                ))}
              </div>
              {voucherBlock && (
                <div className="return-notice">
                  <Ticket size={18} />
                  {voucher ? (
                    <span>
                      Buono <b>{voucher.code}</b> · saldo {euro.format(Number(voucher.current_balance))} di {euro.format(Number(voucher.initial_amount))} · {VOUCHER_STATUS[voucher.status] || voucher.status} · scade il {dateFormat.format(new Date(voucher.expires_at))}
                    </span>
                  ) : (
                    <span>Buono generato per {euro.format(total)}.</span>
                  )}
                </div>
              )}
              {detail.status === "CONFIRMED" && canCancelConfirmed && !detailLoading && (
                voucherUnused ? (
                  cancelOpen ? (
                    <form className="return-cancel-form" onSubmit={cancelConfirmed}>
                      <p>
                        Annullando il reso il capo torna a risultare venduto (esce di nuovo dal magazzino), il buono <b>{voucher.code}</b> viene annullato e al cliente tornano gli eventuali punti stornati. Il reso resta nello storico come annullato.
                      </p>
                      <label className="return-reason">
                        <span>Motivo dell'annullamento</span>
                        <input autoFocus value={cancelReason} maxLength={200} onChange={(event) => setCancelReason(event.target.value)} placeholder="Es. reso registrato per errore" />
                      </label>
                      <div className="return-actions">
                        <button type="button" className="secondary-action return-confirm" disabled={detailBusy} onClick={() => { setCancelOpen(false); setCancelReason(""); setDetailError(""); }}>Indietro</button>
                        <button type="submit" className="primary-action return-confirm" disabled={detailBusy || !cancelReason.trim()}>{detailBusy ? "Annullamento..." : "Conferma annullamento"}</button>
                      </div>
                    </form>
                  ) : (
                    <div className="return-actions">
                      <button className="secondary-action return-confirm" onClick={() => setCancelOpen(true)}><XCircle size={17} /> Annulla reso</button>
                    </div>
                  )
                ) : (
                  <p className="return-detail-note">
                    {voucher ? "Questo reso non si può annullare: il buono è già stato usato, anche in parte, oppure non è più attivo." : "Impossibile verificare il buono: annullamento non disponibile."}
                  </p>
                )
              )}
              {detail.status === "DRAFT" && (
                <>
                  <div className="return-notice">
                    <Ticket size={18} />
                    <span>Questo reso non è stato concluso: il magazzino e il buono non sono ancora stati registrati. Puoi completarlo ora oppure annullare la bozza.</span>
                  </div>
                  <div className="return-actions">
                    <button className="secondary-action return-confirm" disabled={detailBusy} onClick={cancelDraft}><XCircle size={17} /> Annulla bozza</button>
                    <button className="primary-action return-confirm" disabled={detailBusy || !lines.length} onClick={confirmDraft}>{detailBusy ? "Registrazione..." : "Completa reso e genera buono"}</button>
                  </div>
                </>
              )}
            </>
          )}
          {detailError && <p className="return-error">{detailError}</p>}
        </section>
      </section>
    );
  }

  if (wizard) {
    if (completed) {
      return (
        <section className="returns-page return-wizard">
          <article className="return-completed">
            <CheckCircle2 size={38} />
            <p className="eyebrow">Reso confermato</p>
            <h2>{completed.number}</h2>
            <p>
              Il buono di {euro.format(Number(completed.total_refund_amount))} è stato generato
              {completed.voucher_code ? <> con codice <strong>{completed.voucher_code}</strong></> : ""}: consegnalo al cliente.
            </p>
            <div>
              <button className="secondary-action" onClick={resetWizard}>Chiudi</button>
              <button className="primary-action" onClick={() => (onStartExchange && completed.credit?.code ? onStartExchange(completed.credit) : onNavigate("Nuova vendita"))}>
                <RefreshCcw size={17} /> Avvia un cambio
              </button>
            </div>
          </article>
        </section>
      );
    }
    return (
      <section className="returns-page return-wizard">
        <div className="page-title-row">
          <div>
            <p className="eyebrow">Operatività · Resi</p>
            <h2>Apri un nuovo reso</h2>
            <span>Cerca la vendita originale, poi seleziona gli articoli restituiti.</span>
          </div>
          <button className="secondary-action return-back" onClick={resetWizard}><ArrowLeft size={17} /> Torna allo storico</button>
        </div>
        {!selectedSale ? (
          <section className="return-find-sale">
            <PackageSearch size={27} />
            <div>
              <h3>Trova la vendita originale</h3>
              <p>Cerca per scontrino, tessera, cliente, figlio, articolo, marca, SKU o barcode.</p>
            </div>
            <form onSubmit={findSales}>
              <input autoFocus value={saleQuery} onChange={(event) => setSaleQuery(event.target.value)} placeholder="Cerca vendita o articolo" />
              <button className="primary-action">Cerca</button>
            </form>
            {error && <p className="return-error">{error}</p>}
            {sales.length > 0 && (
              <div className="return-sale-results">
                {sales.map((sale) => (
                  <button key={sale.id} onClick={() => selectSale(sale)}>
                    <div>
                      <strong>{sale.number}</strong>
                      <span>{sale.customer_name || "Vendita banco"} · {dateFormat.format(new Date(sale.confirmed_at || sale.opened_at))}</span>
                    </div>
                    <b>{euro.format(Number(sale.final_total_amount))}</b>
                  </button>
                ))}
              </div>
            )}
          </section>
        ) : (
          <section className="return-lines-card">
            <div className="return-sale-summary">
              <div>
                <p className="eyebrow">Vendita selezionata</p>
                <h3>{selectedSale.number}</h3>
                <span>{selectedSale.customer_name || "Vendita senza cliente"} · {dateFormat.format(new Date(selectedSale.confirmed_at || selectedSale.opened_at))}</span>
              </div>
              <button className="secondary-action" onClick={() => setSelectedSale(null)}>Cambia vendita</button>
            </div>
            <label className="return-reason">
              <span>Motivo del reso</span>
              <input value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            <div className="return-lines">
              {selectedSale.lines?.map((line) => {
                const available = returnable[line.id];
                const exhausted = available === 0;
                const selected = selectedLines[line.id];
                return (
                  <label key={line.id} className={exhausted ? "is-disabled" : ""}>
                    <input type="checkbox" disabled={exhausted} checked={Boolean(selected)} onChange={(event) => setLine(line, event.target.checked)} />
                    <div>
                      <strong>{line.product_name_snapshot}</strong>
                      <span>{lineDetails(line)}</span>
                      <span>
                        Acquistati: {line.quantity}
                        {exhausted ? " · già restituito" : available !== undefined && available < line.quantity ? ` · restituibili: ${available}` : ""}
                      </span>
                      {selected && available > 1 && (
                        <span className="return-line-quantity">
                          Quantità da rendere
                          <select value={selected.quantity} onChange={(event) => setLineQuantity(line, Number(event.target.value))}>
                            {Array.from({ length: available }, (_, index) => index + 1).map((value) => <option key={value} value={value}>{value}</option>)}
                          </select>
                        </span>
                      )}
                    </div>
                    <b>{euro.format(Number(line.net_amount))}</b>
                  </label>
                );
              })}
            </div>
            <div className="return-notice">
              <Ticket size={18} />
              <span>
                <b>Il cliente non prende niente:</b> conferma e genera il buono da consegnargli. <b>Cambio</b> (altra taglia o altro articolo): si apre la nuova vendita con il credito già applicato al pagamento; se il nuovo articolo costa di più si paga la differenza, se costa di meno la differenza resta sul buono.
              </span>
            </div>
            {error && <p className="return-error">{error}</p>}
            <div className="return-actions">
              <button className="secondary-action return-confirm" disabled={saving} onClick={() => confirmReturn("voucher")}>{saving ? "Registrazione..." : "Conferma reso e genera buono"}</button>
              <button className="primary-action return-confirm" disabled={saving} onClick={() => confirmReturn("exchange")}><RefreshCcw size={17} /> {saving ? "Registrazione..." : "Conferma e fai il cambio"}</button>
            </div>
          </section>
        )}
      </section>
    );
  }

  return (
    <section className="returns-page">
      <div className="page-title-row">
        <div>
          <p className="eyebrow">Operatività</p>
          <h2>Resi</h2>
          <span>Consulta lo storico dei resi e apri un reso per vederne il dettaglio. Per aprirne uno nuovo, seleziona una vendita dallo Storico vendite.</span>
        </div>
      </div>
      <form className="returns-search" onSubmit={(event) => { event.preventDefault(); loadReturns(); }}>
        <Search size={18} />
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Cerca reso, scontrino, cliente o articolo" />
        <button>Ricerca</button>
      </form>
      <article className="returns-list">
        <div className="returns-heading"><span>Reso</span><span>Stato</span><span>Credito</span></div>
        {loading && <p>Caricamento resi...</p>}
        {error && <p className="return-error">{error}</p>}
        {!loading && !error && !returns.length && <p>Nessun reso corrisponde alla ricerca.</p>}
        {!loading && !error && (
          <PaginatedRows items={returns} resetKey={search}>
            {(rows) => rows.map((item) => (
              <button type="button" className="return-row" key={item.id} onClick={() => openDetail(item)}>
                <div>
                  <strong>{item.number || "Reso in bozza"}</strong>
                  <span>{item.reason || "Reso"} · {dateFormat.format(new Date(item.created_at))}</span>
                </div>
                <span className={`return-status ${item.status.toLowerCase()}`}>{STATUS_LABELS[item.status]}</span>
                <strong>{item.status === "CONFIRMED" ? euro.format(Number(item.total_refund_amount || 0)) : "—"}</strong>
              </button>
            ))}
          </PaginatedRows>
        )}
      </article>
    </section>
  );
}
