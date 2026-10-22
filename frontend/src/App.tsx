import { lazy, Suspense, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Login } from "./features/auth/Login";
import { BankPortal } from "./features/bank-portal/BankPortal";
import { DataView } from "./features/data/DataView";
import { SyncView } from "./features/sync/SyncView";
import { IssuesView } from "./features/issues/IssuesView";
import type { Kind, Session } from "./types";
import "./style.css";
const ProfileView = lazy(() =>
  import("./features/profiling/ProfileView").then((module) => ({
    default: module.ProfileView,
  })),
);
const tabs = [
  { id: "sync", name: "Senkronizasyon", icon: "⇄" },
  { id: "bank", name: "Banka portalı", icon: "▱" },
  { id: "data", name: "Portföy verisi", icon: "▦" },
  { id: "profiling", name: "Veri profili", icon: "▥" },
  { id: "issues", name: "Doğrulama", icon: "✓" },
];
function saved(): Session | null {
  try {
    return JSON.parse(sessionStorage.getItem("ledgerbridge-session") || "null");
  } catch {
    return null;
  }
}
export default function App() {
  const [session, setSession] = useState<Session | null>(saved);
  const [tab, setTab] = useState("sync");
  const [kind, setKind] = useState<Kind>("RETAIL");
  const [issueId, setIssueId] = useState("");
  const cache = useQueryClient();
  function login(value: Session) {
    sessionStorage.setItem("ledgerbridge-session", JSON.stringify(value));
    setSession(value);
  }
  if (!session) return <Login onLogin={login} />;
  const shared = { session, kind };
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          t<span>ledgerbridge</span>
        </div>
        <div className="workspace">
          <span className="bank-avatar">{session.tenant.slice(-2)}</span>
          <div>
            <b>{session.tenant}</b>
            <small>Banka çalışma alanı</small>
          </div>
          <span className="online-dot" />
        </div>
        <span className="nav-label">ÇALIŞMA ALANI</span>
        <nav aria-label="Ana menü">
          {tabs.map((item) => (
            <button
              key={item.id}
              className={tab === item.id ? "active" : ""}
              onClick={() => setTab(item.id)}
            >
              <span>{item.icon}</span>
              {item.name}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <b>Veriniz, kendi alanınızda.</b>
          <p>Yalnızca hesabınıza bağlı bankanın portföyüne erişirsiniz.</p>
        </div>
        <button
          className="logout"
          onClick={() => {
            sessionStorage.removeItem("ledgerbridge-session");
            cache.clear();
            setSession(null);
          }}
        >
          ↪ Oturumu kapat
        </button>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <span>
            Portföy Veri Platformu <i>/</i>{" "}
            {tabs.find((t) => t.id === tab)?.name}
          </span>
          <div className="user-chip">
            <span className="avatar">{session.tenant.slice(-2)}</span>
            <span>
              {session.username}
              <small>Banka kullanıcısı</small>
            </span>
          </div>
        </header>
        <main className="content">
          <div className="page-heading">
            <div>
              <span className="eyebrow">{session.tenant} · ÇALIŞMA ALANI</span>
              <h1>{tabs.find((t) => t.id === tab)?.name}</h1>
            </div>
            <div className="portfolio-picker">
              <span>PORTFÖY</span>
              <select
                aria-label="Kredi tipi"
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value as Kind);
                  setIssueId("");
                }}
              >
                <option value="RETAIL">Bireysel krediler</option>
                <option value="COMMERCIAL">Ticari krediler</option>
              </select>
            </div>
          </div>
          {tab === "sync" && (
            <SyncView
              key={kind}
              {...shared}
              onIssues={(id) => {
                setIssueId(id);
                setTab("issues");
              }}
            />
          )}
          {tab === "bank" && <BankPortal key={kind} {...shared} />}{" "}
          {tab === "data" && <DataView key={kind} {...shared} />}{" "}
          {tab === "profiling" && (
            <Suspense fallback={<p>Grafikler hazırlanıyor…</p>}>
              <ProfileView key={kind} {...shared} />
            </Suspense>
          )}{" "}
          {tab === "issues" && (
            <IssuesView key={kind + issueId} {...shared} runId={issueId} />
          )}
          <footer>
            ledgerbridge · Veri Entegrasyon Adaptörü <span>Yerel demo ortamı</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
