import { useEffect, useState } from "react";
import { login, logout, request } from "./api";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  useEffect(() => { request("/auth/me/").then(setUser).catch(() => {}).finally(() => setChecking(false)); }, []);
  if (checking) return <div className="app-loading">Caricamento...</div>;
  async function handleLogout() {
    try { await logout(); } finally { setUser(null); }
  }
  return user ? <DashboardPage user={user} onLogout={handleLogout} /> : <LoginPage onLogin={async (email, password) => setUser(await login(email, password))} />;
}
