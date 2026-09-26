const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

let accessToken = sessionStorage.getItem("accessToken");

function clearLocalSession() {
  accessToken = null;
  sessionStorage.removeItem("accessToken");
}

function notifySessionExpired() {
  clearLocalSession();
  window.dispatchEvent(new Event("auth:expired"));
}

export async function refreshSession() {
  const refreshed = await fetch(`${API_URL}/auth/refresh/`, { method: "POST", credentials: "include" });
  if (!refreshed.ok) {
    notifySessionExpired();
    return false;
  }
  accessToken = (await refreshed.json()).access;
  sessionStorage.setItem("accessToken", accessToken);
  return true;
}

export async function request(path, options = {}) {
  const headers = new Headers(options.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response = await fetch(`${API_URL}${path}`, { ...options, headers, credentials: "include" });
  if (response.status === 401 && path !== "/auth/refresh/") {
    if (await refreshSession()) {
      headers.set("Authorization", `Bearer ${accessToken}`);
      response = await fetch(`${API_URL}${path}`, { ...options, headers, credentials: "include" });
    }
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const details = body.error?.details;
    const readable = details && (typeof details === "string" ? details : Object.values(details).flat().join(" "));
    throw new Error(readable || body.error?.message || body.detail || "Operazione non riuscita.");
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
  const headers = new Headers();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_URL}${path}`, { ...options, headers, credentials: "include" });
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
