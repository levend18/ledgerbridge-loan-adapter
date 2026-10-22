import { useState, type FormEvent } from "react";
import { request, sessionFromToken } from "../../api";
import type { Session } from "../../types";
export function Login({ onLogin }: { onLogin: (session: Session) => void }) {
  const [username, setUsername] = useState("bank001_user");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const data = await request<{ access: string }>(
        "/api/auth/token",
        undefined,
        { username, password },
      );
      onLogin(sessionFromToken(data.access, username));
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-story">
        <div className="brand">
          L<span>LedgerBridge</span>
        </div>
        <span className="eyebrow">VERİNİZE GÜVENLE BAĞLANIN</span>
        <h1>
          Dağınık veriden,
          <br />
          <em>net bir portföye.</em>
        </h1>
        <p>
          Banka verilerini doğrulayın, güncel portföyünüzü izleyin ve her
          değişikliğin kaynağını görün.
        </p>
        <div className="story-grid">
          <div>
            <b>03</b>
            <span>Banka bağlantısı</span>
          </div>
          <div>
            <b>02</b>
            <span>Kredi portföyü</span>
          </div>
          <div>
            <b>01</b>
            <span>Güvenilir görünüm</span>
          </div>
        </div>
        <small>Tenant izolasyonu · İzlenebilir doğrulama · Atomik yayın</small>
      </section>
      <section className="login-panel">
        <div className="login-form">
          <span className="eyebrow">PORTFÖY VERİ PLATFORMU</span>
          <h2>Tekrar hoş geldiniz</h2>
          <p>Bankanıza ait çalışma alanına giriş yapın.</p>
          <form onSubmit={submit}>
            <label>
              Kullanıcı adı
              <input
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </label>
            <label>
              Şifre
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button className="primary" disabled={pending}>
              {pending ? "Giriş yapılıyor…" : "Çalışma alanına gir →"}
            </button>
          </form>
          <aside className="demo-note">
            Demo erişimi
            <br />
            <code>bank001_user / demo1234</code>
            <small>
              Banka 002 ve 003 için kullanıcı adındaki numarayı değiştirin.
            </small>
          </aside>
        </div>
      </section>
    </main>
  );
}
