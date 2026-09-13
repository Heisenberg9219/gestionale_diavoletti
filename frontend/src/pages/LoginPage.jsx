import {
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useState } from "react";
import brandLogo from "../assets/diavoletti-logo.jpg";
import transparentBrandLogo from "../assets/diavoletti-logo-transparent.png";

export default function LoginPage({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await onLogin(email, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-art">
        <div className="art-topline">
          <div className="brand-line"><span><Sparkles size={15} /></span>GESTIONALE</div>
        </div>
        <div className="art-center">
          <div className="logo-stage">
            <picture>
              <source media="(max-width: 500px)" srcSet={transparentBrandLogo} />
              <img src={brandLogo} alt="I Diavoletti" />
            </picture>
          </div>
        </div>
        <div className="art-bottomline">
          <div className="brand-line"><span><ShieldCheck size={15} /></span>NEGOZIO · MAGAZZINO · CLIENTI</div>
          <p>Powered by <strong>Mario Gianfagna</strong></p>
        </div>
      </section>
      <section className="login-panel">
        <form className="login-content" onSubmit={submit}>
          <div className="login-heading"><p>Benvenuto</p><h1>Accedi al gestionale</h1><span>Usa le credenziali personali del negozio.</span></div>
          <label>Email<span className="input-shell"><Mail size={18} /><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" placeholder="nome@negozio.it" required /></span></label>
          <label>Password<span className="input-shell"><LockKeyhole size={18} /><input type={visible ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" placeholder="La tua password" required /><button type="button" onClick={() => setVisible(!visible)} aria-label="Mostra o nascondi password">{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button></span></label>
          {error && <p className="form-error">{error}</p>}
          <button className="login-submit" disabled={loading}>{loading ? "Accesso in corso..." : "Entra"}</button>
          <p className="login-foot"><ShieldCheck size={15} /> Accesso riservato al personale autorizzato</p>
        </form>
        <p className="mobile-powered">Powered by <strong>Mario Gianfagna</strong></p>
      </section>
    </main>
  );
}
