import { useEffect, useState } from "react";
import { Banknote, Calculator, CircleCheck, LockKeyhole, ShoppingBag, UnlockKeyhole } from "lucide-react";
import { request } from "../api";
import "../cash.css";
import "../cash-overrides.css";

const euro = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });

function collection(payload) {
  return payload.results || payload || [];
}

export default function CashPage({ onNavigate }) {
  const [registers, setRegisters] = useState([]);
  const [locations, setLocations] = useState([]);
  const [session, setSession] = useState(null);
  const [openingAmount, setOpeningAmount] = useState("0,00");
  const [countedAmount, setCountedAmount] = useState("");
  const [selectedRegister, setSelectedRegister] = useState("");
  const [registerCode, setRegisterCode] = useState("CASSA-01");
  const [registerName, setRegisterName] = useState("Cassa principale");
  const [registerLocation, setRegisterLocation] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [sessionSales, setSessionSales] = useState(null);
  const [salesFilter, setSalesFilter] = useState("ALL");

  async function loadCash() {
    setLoading(true);
    try {
      const [registerPayload, sessionPayload, locationPayload] = await Promise.all([
        request("/sales/registers/"),
        request("/sales/sessions/"),
        request("/core/locations/?active=true"),
      ]);
      const loadedRegisters = collection(registerPayload);
      const loadedLocations = collection(locationPayload);
      setRegisters(loadedRegisters);
      setLocations(loadedLocations);
      setSelectedRegister((value) => value || loadedRegisters[0]?.id || "");
      setRegisterLocation((value) => value || loadedLocations[0]?.id || "");
      setSession(collection(sessionPayload).find((item) => item.status === "OPEN") || null);
    } catch {
      setError("Non è stato possibile caricare la situazione della cassa.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCash();
  }, []);

  // Incassi della sessione aperta: le vendite confermate di questo registratore da quando è aperta.
  useEffect(() => {
    if (!session) {
      setSessionSales(null);
      return;
    }
    const day = session.opened_at.slice(0, 10);
    request(
      `/sales/sales/?status=CONFIRMED&cash_register=${session.cash_register}&date_from=${day}&page_size=200`,
    )
      .then((payload) =>
        setSessionSales(collection(payload).filter((sale) => sale.cash_session === session.id)),
      )
      .catch(() => setSessionSales([]));
  }, [session]);

  async function openSession(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const opened = await request("/sales/sessions/open/", {
        method: "POST",
        body: JSON.stringify({
          cash_register: selectedRegister,
          opening_cash_amount: openingAmount.replace(",", "."),
        }),
      });
      setSession(opened);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function closeSession(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await request(`/sales/sessions/${session.id}/close/`, {
        method: "POST",
        body: JSON.stringify({ counted_cash_amount: countedAmount.replace(",", ".") }),
      });
      setSession(null);
      setCountedAmount("");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function createRegister(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const created = await request("/sales/registers/", {
        method: "POST",
        body: JSON.stringify({
          code: registerCode,
          name: registerName,
          location: registerLocation,
          is_active: true,
        }),
      });
      setRegisters([created]);
      setSelectedRegister(created.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const activeRegister = registers.find((item) => item.id === session?.cash_register);
  return (
    <section className="cash-page">
      <div className="page-title-row">
        <div>
          <p className="eyebrow">Operatività</p>
          <h2>Cassa</h2>
          <span>Apri, controlla e chiudi la sessione del registratore.</span>
        </div>
        {session && (
          <button className="primary-action" onClick={() => onNavigate("Nuova vendita")}>
            <ShoppingBag size={18} /> Nuova vendita
          </button>
        )}
      </div>
      {loading ? (
        <p className="cash-message">Caricamento cassa...</p>
      ) : error ? (
        <p className="cash-error">{error}</p>
      ) : session ? (
        <>
          {(() => {
            const expected =
              session.expected_cash_amount != null
                ? Number(session.expected_cash_amount)
                : Number(session.opening_cash_amount || 0) +
                  Number(session.cash_payments_total || 0) +
                  Number(session.other_cash_total || 0);
            const counted = Number(String(countedAmount).replace(",", "."));
            const hasCount = countedAmount.trim() !== "" && Number.isFinite(counted);
            const difference = hasCount ? Math.round((counted - expected) * 100) / 100 : null;
            const sales = sessionSales || [];
            const methodsOf = (sale) => new Set((sale.payments || []).map((payment) => payment.method));
            const cashCount = sales.filter((sale) => methodsOf(sale).has("CASH")).length;
            const cardCount = sales.filter((sale) => methodsOf(sale).has("CARD")).length;
            const shown = sales.filter((sale) => salesFilter === "ALL" || methodsOf(sale).has(salesFilter));
            const methodLabel = (sale) =>
              [...methodsOf(sale)]
                .map(
                  (method) =>
                    ({ CASH: "Contanti", CARD: "Carta", GIFT_CARD: "Gift card", STORE_CREDIT: "Buono reso" })[
                      method
                    ] || "Altro",
                )
                .join(" + ") || "—";
            return (
              <>
                <article className="cash-session-status-row">
                  <span className="cash-pill open">
                    <i aria-hidden="true" />
                    <CircleCheck size={16} /> Sessione aperta · {activeRegister?.name || "Registratore"}
                  </span>
                </article>
                <div className="cash-kpis cash-session-values cash-session-payment-values">
                  <div className="cash-kpi">
                    <p>Fondo iniziale</p>
                    <strong>{euro.format(Number(session.opening_cash_amount))}</strong>
                    <small>
                      Aperta alle{" "}
                      {new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" }).format(
                        new Date(session.opened_at),
                      )}
                    </small>
                  </div>
                  <div className="cash-kpi">
                    <p>Pagamenti contanti</p>
                    <strong>{euro.format(Number(session.cash_payments_total || 0))}</strong>
                    {sessionSales && <small>{cashCount} vendite</small>}
                  </div>
                  <div className="cash-kpi">
                    <p>Pagamenti carta</p>
                    <strong>{euro.format(Number(session.card_payments_total || 0))}</strong>
                    {sessionSales && <small>{cardCount} vendite</small>}
                  </div>
                  <div className="cash-kpi">
                    <p>Liste regalo e buoni (contanti)</p>
                    <strong>{euro.format(Number(session.other_cash_total || 0))}</strong>
                  </div>
                  <div className="cash-kpi total">
                    <p>Contante previsto</p>
                    <strong>{euro.format(expected)}</strong>
                    <small>fondo + contanti + buoni</small>
                  </div>
                </div>
                <div className="cash-columns">
                  <section className="cash-panel wide" aria-label="Incassi della sessione">
                    <div className="cash-panel-head">
                      <h3>Incassi della sessione</h3>
                      <div className="seg" role="group" aria-label="Filtra per metodo">
                        {[
                          ["ALL", "Tutti"],
                          ["CASH", "Contanti"],
                          ["CARD", "Carta"],
                        ].map(([value, label]) => (
                          <button
                            key={value}
                            type="button"
                            aria-pressed={salesFilter === value}
                            onClick={() => setSalesFilter(value)}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                    </div>
                    {sessionSales === null ? (
                      <p className="empty-note">Caricamento incassi…</p>
                    ) : shown.length ? (
                      <div className="table-scroll">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Ora</th>
                              <th>Scontrino</th>
                              <th>Cliente</th>
                              <th>Metodo</th>
                              <th className="num">Importo</th>
                            </tr>
                          </thead>
                          <tbody>
                            {shown.map((sale) => (
                              <tr key={sale.id}>
                                <td className="tabular">
                                  {new Intl.DateTimeFormat("it-IT", {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  }).format(new Date(sale.confirmed_at || sale.opened_at))}
                                </td>
                                <td>
                                  <b>{sale.number}</b>
                                </td>
                                <td>{sale.customer_name || "Vendita banco"}</td>
                                <td>{methodLabel(sale)}</td>
                                <td className="num">{euro.format(Number(sale.final_total_amount || 0))}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="empty-note">
                        {sales.length
                          ? "Nessun incasso con questo metodo."
                          : "Nessuna vendita ancora in questa sessione. Le vendite confermate compaiono qui."}
                      </p>
                    )}
                  </section>
                  <form className="cash-panel side cash-close-card" onSubmit={closeSession}>
                    <div>
                      <p className="eyebrow">Fine turno</p>
                      <h3>Chiudi la cassa</h3>
                      <span>Inserisci il contante effettivamente contato.</span>
                    </div>
                    <label>
                      Contante contato
                      <input
                        required
                        inputMode="decimal"
                        value={countedAmount}
                        onChange={(event) => setCountedAmount(event.target.value)}
                        placeholder="0,00"
                      />
                    </label>
                    {difference !== null && (
                      <div className={`cash-diff ${difference === 0 ? "even" : "off"}`} role="status">
                        <div>
                          <span>Contante previsto</span>
                          <span className="money">{euro.format(expected)}</span>
                        </div>
                        <div>
                          <b>Differenza</b>
                          <b className="money">
                            {difference > 0 ? "+" : ""}
                            {euro.format(difference)}
                          </b>
                        </div>
                        <span>
                          {difference === 0
                            ? "Il contante torna con il previsto."
                            : difference < 0
                              ? `Mancano ${euro.format(-difference)} rispetto al previsto: ricontrolla prima di confermare.`
                              : `Ci sono ${euro.format(difference)} in più rispetto al previsto: ricontrolla prima di confermare.`}
                        </span>
                      </div>
                    )}
                    <button className="primary-action" disabled={saving} style={{ justifyContent: "center" }}>
                      <LockKeyhole size={18} />
                      {saving ? "Chiusura..." : "Conferma chiusura"}
                    </button>
                  </form>
                </div>
              </>
            );
          })()}
        </>
      ) : (
        <article className="cash-open-card">
          <div className="cash-open-icon">
            <UnlockKeyhole size={25} />
          </div>
          <div>
            <p className="eyebrow">Inizio turno</p>
            <h3>Apri una sessione di cassa</h3>
            <span>Seleziona il registratore e registra il fondo iniziale.</span>
          </div>
          {!registers.length ? (
            <form className="register-create-form" onSubmit={createRegister}>
              <label>
                Codice registratore
                <input
                  required
                  value={registerCode}
                  onChange={(event) => setRegisterCode(event.target.value)}
                />
              </label>
              <label>
                Nome registratore
                <input
                  required
                  value={registerName}
                  onChange={(event) => setRegisterName(event.target.value)}
                />
              </label>
              <label>
                Sede
                <select
                  required
                  value={registerLocation}
                  onChange={(event) => setRegisterLocation(event.target.value)}
                >
                  <option value="">Seleziona sede</option>
                  {locations.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
                </select>
              </label>
              <button className="primary-action" disabled={saving || !registerLocation}>
                <Calculator size={18} />
                {saving ? "Creazione..." : "Crea registratore"}
              </button>
            </form>
          ) : (
            <form className="open-session-form" onSubmit={openSession}>
              <label>
                Registratore
                <select
                  required
                  value={selectedRegister}
                  onChange={(event) => setSelectedRegister(event.target.value)}
                >
                  <option value="">Seleziona registratore</option>
                  {registers.map((register) => (
                    <option key={register.id} value={register.id}>
                      {register.name || register.code}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Fondo iniziale
                <input
                  required
                  inputMode="decimal"
                  value={openingAmount}
                  onChange={(event) => setOpeningAmount(event.target.value)}
                />
              </label>
              <button className="primary-action" disabled={saving || !selectedRegister}>
                <Banknote size={18} />
                {saving ? "Apertura..." : "Apri cassa"}
              </button>
            </form>
          )}
        </article>
      )}
    </section>
  );
}
