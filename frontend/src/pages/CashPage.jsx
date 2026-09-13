import { useEffect, useState } from "react";
import { Banknote, Calculator, CircleCheck, LockKeyhole, ShoppingBag, UnlockKeyhole } from "lucide-react";
import { request } from "../api";
import "../cash.css";
import "../cash-overrides.css";

const euro = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });

function collection(payload) { return payload.results || payload || []; }

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

  async function loadCash() {
    setLoading(true);
    try {
      const [registerPayload, sessionPayload, locationPayload] = await Promise.all([request("/sales/registers/"), request("/sales/sessions/"), request("/core/locations/?active=true")]);
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

  useEffect(() => { loadCash(); }, []);

  async function openSession(event) {
    event.preventDefault();
    setSaving(true); setError("");
    try {
      const opened = await request("/sales/sessions/open/", { method: "POST", body: JSON.stringify({ cash_register: selectedRegister, opening_cash_amount: openingAmount.replace(",", ".") }) });
      setSession(opened);
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  }

  async function closeSession(event) {
    event.preventDefault();
    setSaving(true); setError("");
    try {
      await request(`/sales/sessions/${session.id}/close/`, { method: "POST", body: JSON.stringify({ counted_cash_amount: countedAmount.replace(",", ".") }) });
      setSession(null); setCountedAmount("");
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  }

  async function createRegister(event) {
    event.preventDefault();
    setSaving(true); setError("");
    try {
      const created = await request("/sales/registers/", { method: "POST", body: JSON.stringify({ code: registerCode, name: registerName, location: registerLocation, is_active: true }) });
      setRegisters([created]); setSelectedRegister(created.id);
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  }

  const activeRegister = registers.find((item) => item.id === session?.cash_register);
  return <section className="cash-page">
    <div className="page-title-row"><div><p className="eyebrow">Operatività</p><h2>Cassa</h2><span>Apri, controlla e chiudi la sessione del registratore.</span></div>{session && <button className="primary-action" onClick={() => onNavigate("Nuova vendita")}><ShoppingBag size={18} /> Nuova vendita</button>}</div>
    {loading ? <p className="cash-message">Caricamento cassa...</p> : error ? <p className="cash-error">{error}</p> : session ? <>
      <article className="cash-session-card">
        <div className="cash-session-status"><span><CircleCheck size={18} /> Sessione aperta</span><strong>{activeRegister?.name || "Registratore"}</strong></div>
        <div className="cash-session-values"><div><p>Fondo iniziale</p><strong>{euro.format(Number(session.opening_cash_amount))}</strong></div><div><p>Contante previsto</p><strong>{euro.format(Number(session.expected_cash_amount || 0))}</strong></div><div><p>Aperta alle</p><strong>{new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" }).format(new Date(session.opened_at))}</strong></div></div>
      </article>
      <form className="cash-close-card" onSubmit={closeSession}><div><p className="eyebrow">Fine turno</p><h3>Chiudi la cassa</h3><span>Inserisci il contante effettivamente contato.</span></div><label>Contante contato<input required inputMode="decimal" value={countedAmount} onChange={(event) => setCountedAmount(event.target.value)} placeholder="0,00" /></label><button className="secondary-action" disabled={saving}><LockKeyhole size={18} />{saving ? "Chiusura..." : "Conferma chiusura"}</button></form>
    </> : <article className="cash-open-card"><div className="cash-open-icon"><UnlockKeyhole size={25} /></div><div><p className="eyebrow">Inizio turno</p><h3>Apri una sessione di cassa</h3><span>Seleziona il registratore e registra il fondo iniziale.</span></div>{!registers.length ? <form className="register-create-form" onSubmit={createRegister}><label>Codice registratore<input required value={registerCode} onChange={(event) => setRegisterCode(event.target.value)} /></label><label>Nome registratore<input required value={registerName} onChange={(event) => setRegisterName(event.target.value)} /></label><label>Sede<select required value={registerLocation} onChange={(event) => setRegisterLocation(event.target.value)}><option value="">Seleziona sede</option>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label><button className="primary-action" disabled={saving || !registerLocation}><Calculator size={18} />{saving ? "Creazione..." : "Crea registratore"}</button></form> : <form className="open-session-form" onSubmit={openSession}><label>Registratore<select required value={selectedRegister} onChange={(event) => setSelectedRegister(event.target.value)}><option value="">Seleziona registratore</option>{registers.map((register) => <option key={register.id} value={register.id}>{register.name || register.code}</option>)}</select></label><label>Fondo iniziale<input required inputMode="decimal" value={openingAmount} onChange={(event) => setOpeningAmount(event.target.value)} /></label><button className="primary-action" disabled={saving || !selectedRegister}><Banknote size={18} />{saving ? "Apertura..." : "Apri cassa"}</button></form>}</article>}
  </section>;
}
