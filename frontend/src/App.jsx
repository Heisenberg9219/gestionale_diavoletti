import { useEffect, useState } from "react";
import { login, logout, request } from "./api";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";

const IDLE_TIMEOUT_MINUTES = Number(import.meta.env.VITE_IDLE_TIMEOUT_MINUTES || 30);
const IDLE_TIMEOUT_MS = IDLE_TIMEOUT_MINUTES * 60 * 1000;

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  useEffect(() => { request("/auth/me/").then(setUser).catch(() => {}).finally(() => setChecking(false)); }, []);
  useEffect(() => {
    const handleExpiredSession = () => setUser(null);
    window.addEventListener("auth:expired", handleExpiredSession);
    return () => window.removeEventListener("auth:expired", handleExpiredSession);
  }, []);
  useEffect(() => {
    if (!user) return undefined;
    let timer;
    const resetTimer = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        logout().finally(() => setUser(null));
      }, IDLE_TIMEOUT_MS);
    };
    const activityEvents = ["pointerdown", "keydown", "touchstart"];
    activityEvents.forEach((eventName) => window.addEventListener(eventName, resetTimer));
    resetTimer();
    return () => {
      window.clearTimeout(timer);
      activityEvents.forEach((eventName) => window.removeEventListener(eventName, resetTimer));
    };
  }, [user]);
  if (checking) return <div className="app-loading">Caricamento...</div>;
  async function handleLogout() {
    try { await logout(); } finally { setUser(null); }
  }
  return user ? <DashboardPage user={user} onLogout={handleLogout} /> : <LoginPage onLogin={async (email, password) => setUser(await login(email, password))} />;
}
