import { useEffect, useState } from "react";
import { LockKeyhole, Pencil, Plus, ShieldCheck, Trash2, UserRoundCog, X } from "lucide-react";
import { request } from "../api";
import "../products.css";

const list = (data) => data?.results || data || [];
const blank = { first_name: "", last_name: "", email: "", password: "", role_names: ["Commesso"], status: "ACTIVE" };
const statusLabel = { INVITED: "Invitato", ACTIVE: "Attivo", BLOCKED: "Bloccato", ARCHIVED: "Archiviato" };

export default function UsersRolesPage({ currentUser }) {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [selected, setSelected] = useState([]);
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);
  const [permissionUser, setPermissionUser] = useState(null);
  const [permissions, setPermissions] = useState([]);
  const [permissionsSaving, setPermissionsSaving] = useState(false);
  const availableRoles = roles.length ? roles : [{ name: "Titolare", description: "Accesso completo a dati e configurazione." }, { name: "Commesso", description: "Accesso alle funzioni operative di negozio." }];

  const notice = (text, ok = true) => { setSuccess(ok); setMessage(text); };
  const load = async () => {
    try {
      const [userData, roleData] = await Promise.all([request("/auth/users/"), request("/auth/roles/")]);
      setUsers(list(userData)); setRoles(list(roleData));
    } catch (error) { notice(error.message || "Impossibile caricare gli utenti.", false); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!message) return undefined; const timer = setTimeout(() => setMessage(""), 4000); return () => clearTimeout(timer); }, [message]);
  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));
  const toggle = (id) => setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  const toggleAll = () => setSelected(selected.length === users.length ? [] : users.map((user) => user.id));
  const openCreate = () => { setEditing(null); setForm(blank); setMessage(""); setFormOpen(true); };
  const openEdit = (user) => { setEditing(user); setForm({ first_name: user.first_name || "", last_name: user.last_name || "", email: user.email, password: "", role_names: user.roles?.length ? user.roles : ["Commesso"], status: user.status }); setMessage(""); setFormOpen(true); };
  async function save(event) {
    event.preventDefault(); setSaving(true);
    try {
      const payload = { ...form, first_name: form.first_name.trim(), last_name: form.last_name.trim(), email: form.email.trim().toLowerCase() };
      delete payload.status;
      if (editing && !payload.password) delete payload.password;
      const saved = await request(editing ? `/auth/users/${editing.id}/` : "/auth/users/", { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload) });
      setFormOpen(false); notice(editing ? "Utente aggiornato correttamente." : "Utente creato correttamente."); await load();
      if (saved.roles?.includes("Commesso")) await loadPermissions(saved);
    } catch (error) { notice(error.message, false); } finally { setSaving(false); }
  }
  async function setStatus(usersToUpdate, status) {
    try { await Promise.all(usersToUpdate.map((user) => request(`/auth/users/${user.id}/`, { method: "PATCH", body: JSON.stringify({ status }) }))); setSelected([]); notice(status === "BLOCKED" ? "Utenti selezionati bloccati." : "Utenti selezionati riattivati."); await load(); }
    catch (error) { notice(error.message, false); }
  }
  async function archiveUsers(targets) {
    if (!targets.length || !window.confirm("Archiviare gli utenti selezionati?")) return;
    try { await Promise.all(targets.map((user) => request(`/auth/users/${user.id}/`, { method: "DELETE" }))); setSelected([]); notice("Utenti archiviati correttamente."); await load(); }
    catch (error) { notice(error.message, false); }
  }
  const archiveSelected = () => archiveUsers(users.filter((user) => selected.includes(user.id)));
  async function loadPermissions(user) {
    try { setPermissionUser(user); setPermissions(list(await request(`/auth/users/${user.id}/page-permissions/`))); }
    catch (error) { notice(error.message, false); }
  }
  function togglePermission(pageKey, field) {
    setPermissions((current) => current.map((item) => item.page_key !== pageKey ? item : { ...item, [field]: !item[field], can_view: field === "can_view" ? !item.can_view : true }));
  }
  async function savePermissions() {
    setPermissionsSaving(true);
    try { const saved = await request(`/auth/users/${permissionUser.id}/page-permissions/`, { method: "PATCH", body: JSON.stringify({ permissions }) }); setPermissions(list(saved)); notice("Permessi del commesso salvati correttamente."); }
    catch (error) { notice(error.message, false); } finally { setPermissionsSaving(false); }
  }

  return <section className="products-page users-roles-page">
    <style>{`.user-form{display:grid;grid-template-columns:1.25fr repeat(4,minmax(120px,1fr));gap:14px;align-items:end;padding:20px;border-radius:14px;background:#fff;box-shadow:0 7px 22px #25171a09}.user-form label{display:grid;gap:6px;font-size:11px;font-weight:900}.user-form input,.user-form select{box-sizing:border-box;width:100%;height:42px;border:1px solid #ded9db;border-radius:8px;padding:0 10px;background:#fff;font:inherit}.user-copy{grid-row:span 2}.roles-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:18px 0}.roles-summary article{display:flex;align-items:flex-start;gap:12px;padding:17px;border:1px solid #e8e2e4;border-radius:8px;background:#fff;box-shadow:0 7px 22px #25171a09}.roles-summary svg{color:#d8001d}.roles-summary strong{display:block;margin-bottom:4px;font-size:14px}.roles-summary span{color:#777176;font-size:12px}.permissions-panel{margin:18px 0;padding:20px;border:1px solid #e8e2e4;border-radius:8px;background:#fff;box-shadow:0 7px 22px #25171a09}.permissions-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:15px}.permissions-heading h3{margin:0 0 4px;font-size:17px}.permissions-heading span{color:#777176;font-size:12px}.permissions-table{overflow:auto;border:1px solid #eee9eb;border-radius:8px}.permissions-row{display:grid;grid-template-columns:minmax(180px,1fr) repeat(4,112px);align-items:center;border-top:1px solid #eee9eb;min-width:628px}.permissions-row:first-child{border-top:0}.permissions-row>span{padding:12px 14px;font-size:12px}.permissions-row.header{background:#faf8f9;color:#8b858a;font-size:10px;font-weight:900;letter-spacing:.06em;text-transform:uppercase}.permissions-row.header>span:not(:first-child){padding-right:8px;padding-left:8px;text-align:center;white-space:nowrap}.permissions-row label{display:grid;place-items:center;padding:12px}.permissions-row input{width:17px;height:17px;margin:0;accent-color:#ed001b;cursor:pointer}.users-heading,.user-row{display:grid;grid-template-columns:34px minmax(180px,1.2fr) minmax(130px,.8fr) 120px 140px;gap:18px;align-items:center;padding:15px 22px}.users-heading{color:#8b858a;font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase}.user-row{border-top:1px solid #eeeaea}.user-row.selected{background:#edf8f7}.user-row>div{display:grid;gap:4px}.user-row strong{font-size:13px}.user-row span{color:#817b80;font-size:12px}.user-check{display:grid!important;place-items:center}.user-check input{width:17px;height:17px;accent-color:#178c82;cursor:pointer}.user-role{justify-self:start;padding:5px 8px;border-radius:7px;background:#f1eff0;color:#625b60;font-size:10px;font-style:normal;font-weight:900}.user-role.owner{background:#fff0f2;color:#b00019}.user-status{justify-self:start;padding:5px 8px;border-radius:7px;background:#edf9f1;color:#167444;font-size:10px;font-style:normal;font-weight:900}.user-status.blocked{background:#fff0f2;color:#b00019}.user-actions{display:flex!important;justify-content:flex-end;gap:7px}.user-actions button{display:grid;width:32px;height:32px;place-items:center;border:1px solid #e2dddf;border-radius:7px;background:#fff;color:#4d464c;cursor:pointer}.user-actions button:hover{border-color:#ed001b;color:#b70018}@media(max-width:900px){.user-form{grid-template-columns:1fr 1fr}.user-copy{grid-column:1/-1;grid-row:auto}.users-heading{display:none}.user-row{grid-template-columns:28px 1fr auto;padding:16px}.user-row>span,.user-row>em{display:none}.user-check{grid-column:1;grid-row:1}.user-row>div:nth-child(2){grid-column:2;grid-row:1}.user-actions{grid-column:3;grid-row:1}.user-role{grid-column:2;grid-row:2}}@media(max-width:600px){.user-form{grid-template-columns:1fr}.user-form .inline-form-actions button{flex:1}.roles-summary{grid-template-columns:1fr}.permissions-heading{align-items:stretch;flex-direction:column}}`}</style>
    <div className="page-title-row"><div><p className="eyebrow">Controllo</p><h2>Utenti e ruoli</h2><span>Gestisci gli accessi del personale e le autorizzazioni del gestionale.</span></div><button className="primary-action" onClick={openCreate}><Plus size={17} /> Nuovo utente</button></div>
    {formOpen && <form className="user-form" onSubmit={save}><div className="inventory-form-copy user-copy"><p className="eyebrow">{editing ? "Modifica utente" : "Nuovo utente"}</p><h3>{editing ? "Aggiorna accesso" : "Crea un accesso"}</h3><span>Il ruolo definisce ciò che il personale può vedere e modificare.</span></div><label>Nome<input required value={form.first_name} onChange={(event) => update("first_name", event.target.value)} /></label><label>Cognome<input required value={form.last_name} onChange={(event) => update("last_name", event.target.value)} /></label><label>Email<input required type="email" value={form.email} onChange={(event) => update("email", event.target.value)} /></label><label>Ruolo<select value={form.role_names[0]} onChange={(event) => update("role_names", [event.target.value])}>{availableRoles.map((role) => <option key={role.name} value={role.name}>{role.name}</option>)}</select></label><label>Password {editing && "(lascia vuoto per non cambiarla)"}<input required={!editing} minLength="8" type="password" value={form.password} onChange={(event) => update("password", event.target.value)} placeholder={editing ? "Non modificata" : "Almeno 8 caratteri"} /></label><div className="inline-form-actions"><button className="secondary-action" type="button" onClick={() => setFormOpen(false)}><X size={17} /> Annulla</button><button className="primary-action" disabled={saving}>{saving ? "Salvataggio..." : editing ? "Salva modifiche" : "Crea utente"}</button></div></form>}
    {message && <p className={success ? "operation-success" : "catalog-error"}>{message}</p>}
    <section className="roles-summary">{availableRoles.map((role) => <article key={role.name}><ShieldCheck size={21} /><div><strong>{role.name}</strong><span>{role.description || (role.name === "Titolare" ? "Accesso completo a dati e configurazione." : "Accesso alle funzioni operative di negozio.")}</span></div></article>)}</section>
    {permissionUser && <section className="permissions-panel"><div className="permissions-heading"><div><p className="eyebrow">Permessi commesso</p><h3>{permissionUser.first_name || permissionUser.email}</h3><span>Seleziona quali pagine può usare e quali operazioni può eseguire.</span></div><button className="primary-action" type="button" disabled={permissionsSaving} onClick={savePermissions}>{permissionsSaving ? "Salvataggio..." : "Salva permessi"}</button></div><div className="permissions-table"><div className="permissions-row header"><span>Pagina</span><span>Visualizza</span><span>Crea</span><span>Modifica</span><span>Elimina</span></div>{permissions.map((item) => <div className="permissions-row" key={item.page_key}><span>{item.label}</span>{["can_view", "can_create", "can_update", "can_delete"].map((field) => <label key={field}><input type="checkbox" aria-label={`${field} ${item.label}`} checked={item[field]} onChange={() => togglePermission(item.page_key, field)} /></label>)}</div>)}</div></section>}
    {selected.length > 0 && <div className="table-selection-actions"><span>{selected.length} {selected.length === 1 ? "utente selezionato" : "utenti selezionati"}</span><button type="button" onClick={() => setSelected([])}>Deseleziona</button><button type="button" onClick={() => setStatus(users.filter((user) => selected.includes(user.id)), "ACTIVE")}><ShieldCheck size={16} /> Attiva</button><button type="button" onClick={() => setStatus(users.filter((user) => selected.includes(user.id)), "BLOCKED")}><LockKeyhole size={16} /> Blocca</button><button type="button" className="delete-selected" onClick={archiveSelected}><Trash2 size={16} /> Archivia</button></div>}
    <article className="products-list"><div className="users-heading"><span className="user-check"><input type="checkbox" aria-label="Seleziona tutti gli utenti" checked={users.length > 0 && selected.length === users.length} onChange={toggleAll} /></span><span>Utente</span><span>Ruolo</span><span>Stato</span><span>Azioni</span></div>{!users.length ? <div className="empty-product-state"><UserRoundCog size={28} /><strong>Nessun utente disponibile</strong><span>Crea il primo accesso per il personale del negozio.</span></div> : users.map((user) => <div className={selected.includes(user.id) ? "user-row selected" : "user-row"} key={user.id}><span className="user-check"><input type="checkbox" aria-label={`Seleziona ${user.email}`} checked={selected.includes(user.id)} onChange={() => toggle(user.id)} /></span><div><strong>{[user.first_name, user.last_name].filter(Boolean).join(" ") || "Utente senza nome"}{user.id === currentUser?.id ? " (tu)" : ""}</strong><span>{user.email}</span></div><em className={`user-role ${user.roles?.includes("Titolare") ? "owner" : ""}`}>{user.roles?.join(", ") || "Nessun ruolo"}</em><em className={`user-status ${user.status.toLowerCase()}`}>{statusLabel[user.status] || user.status}</em><div className="user-actions"><button title="Modifica utente" onClick={() => openEdit(user)}><Pencil size={16} /></button>{user.roles?.includes("Commesso") && <button title="Gestisci permessi" onClick={() => loadPermissions(user)}><ShieldCheck size={16} /></button>}{user.id !== currentUser?.id && <button title="Archivia utente" onClick={() => archiveUsers([user])}><Trash2 size={16} /></button>}</div></div>)}</article>
  </section>;
}
