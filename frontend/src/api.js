const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

let accessToken = sessionStorage.getItem("accessToken");
// Un solo rinnovo di sessione alla volta: le richieste parallele attendono lo
// stesso esito invece di usare due volte il refresh token (che viene ruotato).
let refreshInFlight = null;

function clearLocalSession() {
  accessToken = null;
  sessionStorage.removeItem("accessToken");
}

function notifySessionExpired() {
  clearLocalSession();
  window.dispatchEvent(new Event("auth:expired"));
}

async function performRefresh() {
  const refreshed = await fetch(`${API_URL}/auth/refresh/`, { method: "POST", credentials: "include" });
  if (!refreshed.ok) {
    // 429 = troppi rinnovi ravvicinati: non è una sessione scaduta.
    if (refreshed.status !== 429) notifySessionExpired();
    return false;
  }
  accessToken = (await refreshed.json()).access;
  sessionStorage.setItem("accessToken", accessToken);
  return true;
}

export function refreshSession() {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh()
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

async function authorizedFetch(path, options = {}) {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const send = () => {
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    else headers.delete("Authorization");
    return fetch(`${API_URL}${path}`, { ...options, headers, credentials: "include" });
  };
  const tokenUsed = accessToken;
  let response = await send();
  if (response.status === 401 && path !== "/auth/refresh/" && path !== "/auth/login/") {
    // Se un'altra richiesta ha già rinnovato il token, basta riprovare.
    const renewed = accessToken && accessToken !== tokenUsed ? true : await refreshSession();
    if (renewed) response = await send();
  }
  return response;
}

export async function request(path, options = {}) {
  const response = await authorizedFetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const details = body.error?.details;
    const readable =
      details && (typeof details === "string" ? details : Object.values(details).flat().join(" "));
    const fallback =
      response.status >= 500
        ? "Errore del server durante l'operazione. Riprova dopo aver aggiornato il backend."
        : `Operazione non riuscita (HTTP ${response.status}).`;
    throw new Error(readable || body.error?.message || body.detail || fallback);
  }
  return response.status === 204 ? null : response.json();
}

export async function login(email, password) {
  const result = await request("/auth/login/", { method: "POST", body: JSON.stringify({ email, password }) });
  accessToken = result.access;
  sessionStorage.setItem("accessToken", accessToken);
  return result.user;
}

export async function logout() {
  try {
    await fetch(`${API_URL}/auth/logout/`, { method: "POST", credentials: "include" });
  } finally {
    clearLocalSession();
  }
}

export async function downloadFile(path, filename, options = {}) {
  const response = await authorizedFetch(path, options);
  if (!response.ok) throw new Error("Non è stato possibile preparare il file CSV.");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// Apre in una nuova scheda un allegato protetto (es. PDF fattura).
// La scheda viene aperta subito per non essere bloccata dal browser.
export async function openProtectedFile(path) {
  const preview = window.open("", "_blank");
  try {
    const response = await authorizedFetch(path);
    if (!response.ok) throw new Error("Non è stato possibile aprire il file.");
    const url = URL.createObjectURL(await response.blob());
    if (preview) preview.location.href = url;
    else window.location.assign(url);
    window.setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (error) {
    if (preview) preview.close();
    throw error;
  }
}
