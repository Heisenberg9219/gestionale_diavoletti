import { ArrowRight, Eye, EyeOff, LockKeyhole, Mail, ShieldCheck } from "lucide-react";
import { useState } from "react";
import transparentBrandLogo from "../assets/diavoletti-logo-transparent.png";

// Ultima email usata su questo computer: solo una comodità, se il browser non la salva si riscrive.
const EMAIL_KEY = "diavoletti:last-email";
function readLastEmail() {
  try {
    return window.localStorage.getItem(EMAIL_KEY) || "";
  } catch {
    return "";
  }
}
function saveLastEmail(value) {
  try {
    window.localStorage.setItem(EMAIL_KEY, value);
  } catch {
    // archiviazione non disponibile: nessun problema
  }
}
function greeting() {
  const hour = new Date().getHours();
  if (hour < 13) return "Buongiorno";
  if (hour < 18) return "Buon pomeriggio";
  return "Buonasera";
}

export default function LoginPage({ onLogin }) {
  const [email, setEmail] = useState(readLastEmail);
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [capsLock, setCapsLock] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await onLogin(email, password);
      saveLastEmail(email.trim());
    } catch (err) {
      setError(err.message);
      setPassword("");
    } finally {
      setLoading(false);
    }
  }
  const checkCaps = (event) => setCapsLock(Boolean(event.getModifierState?.("CapsLock")));

  return (
    <main className="signin">
      <section className="signin-brand" aria-label="I Diavoletti">
        <p className="signin-kicker">Gestionale del negozio</p>
        <img className="signin-logo" src={transparentBrandLogo} alt="I Diavoletti" />
        <ul className="signin-areas" aria-label="Aree del gestionale">
          <li>Negozio</li>
          <li>Magazzino</li>
          <li>Clienti</li>
        </ul>
        <p className="signin-powered">
          Powered by <strong>Mario Gianfagna</strong>
        </p>
      </section>
      <section className="signin-panel">
        <form className="signin-form" onSubmit={submit}>
          <div className="signin-heading">
            <p>{greeting()}</p>
            <h1>Accedi al gestionale</h1>
            <span>Usa le credenziali personali del negozio.</span>
          </div>
          <label className="signin-field">
            Email
            <span className="signin-input">
              <Mail size={18} aria-hidden="true" />
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                autoFocus={!email}
                placeholder="nome@negozio.it"
                required
              />
            </span>
          </label>
          <label className="signin-field">
            Password
            <span className="signin-input">
              <LockKeyhole size={18} aria-hidden="true" />
              <input
                type={visible ? "text" : "password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                onKeyDown={checkCaps}
                onKeyUp={checkCaps}
                autoComplete="current-password"
                autoFocus={Boolean(email)}
                placeholder="La tua password"
                required
              />
              <button
                type="button"
                className="signin-eye"
                onClick={() => setVisible(!visible)}
                aria-label="Mostra o nascondi password"
                title={visible ? "Nascondi password" : "Mostra password"}
              >
                {visible ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </span>
            {capsLock && <small className="signin-caps">Maiuscole attive</small>}
          </label>
          {error && (
            <p className="signin-error" role="alert">
              {error}
            </p>
          )}
          <button className="signin-submit" disabled={loading}>
            {loading ? (
              "Accesso in corso..."
            ) : (
              <>
                Entra <ArrowRight size={18} aria-hidden="true" />
              </>
            )}
          </button>
          <p className="signin-foot">
            <ShieldCheck size={15} aria-hidden="true" /> Accesso riservato al personale autorizzato
          </p>
        </form>
        <p className="signin-powered mobile">
          Powered by <strong>Mario Gianfagna</strong>
        </p>
      </section>
    </main>
  );
}
