import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { request, terminal } from "../../api";
import type { Kind, Page, Run, Session } from "../../types";
export function Status({ status }: { status: string }) {
  return (
    <span className={`status status-${status.toLowerCase()}`}>{status}</span>
  );
}
export function SyncView({
  session,
  kind,
  onIssues,
}: {
  session: Session;
  kind: Kind;
  onIssues: (id: string) => void;
}) {
  const cache = useQueryClient();
  const [active, setActive] = useState("");
  const [pending, setPending] = useState(false);
  const [force, setForce] = useState(false);
  const [error, setError] = useState("");
  const runs = useQuery({
    queryKey: ["runs", session.tenant, kind],
    queryFn: () =>
      request<{ results: Run[]; source_versions: Record<Kind, number | null> }>(
        `/api/runs?loan_type=${kind}`,
        session,
      ),
    refetchInterval: 5000,
  });
  const data = useQuery({
    queryKey: ["snapshot", session.tenant, kind],
    queryFn: () =>
      request<Page>(`/api/data?loan_type=${kind}&limit=1`, session),
    retry: false,
  });
  const current = useQuery({
    queryKey: ["run", session.tenant, active],
    queryFn: () => request<Run>(`/api/sync/${active}`, session),
    enabled: !!active,
    refetchInterval: (q) => (terminal(q.state.data?.status) ? false : 1000),
  });
  useEffect(() => {
    if (terminal(current.data?.status)) {
      for (const key of ["runs", "snapshot", "data", "profiles"]) {
        cache.invalidateQueries({ queryKey: [key, session.tenant] });
      }
    }
  }, [current.data?.status, cache, session.tenant]);
  async function start() {
    setPending(true);
    setError("");
    try {
      const result = await request<{ sync_run_id: string }>(
        "/api/sync",
        session,
        { loan_type: kind, force },
      );
      setActive(result.sync_run_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  const last = current.data || runs.data?.results[0];
  const busy = pending || (!!last && !terminal(last.status));
  return (
    <section>
      <div className="section-heading">
        <div>
          <h2>Veri akışınız kontrol altında</h2>
          <p>
            Bankadaki değişiklikleri doğrulayın ve portföye güvenle yayınlayın.
          </p>
        </div>
        <span className="live-indicator">● Otomatik kontrol açık</span>
      </div>
      <div className="kpi-grid">
        <article>
          <span>Yayındaki krediler</span>
          <strong>
            {data.data?.snapshot.row_counts.credit?.toLocaleString("tr-TR") ??
              "—"}
          </strong>
          <small>
            {kind === "RETAIL" ? "Bireysel portföy" : "Ticari portföy"}
          </small>
        </article>
        <article>
          <span>Ödeme planı kayıtları</span>
          <strong>
            {data.data?.snapshot.row_counts.payment_plan?.toLocaleString(
              "tr-TR",
            ) ?? "—"}
          </strong>
          <small>Aynı snapshot içinde</small>
        </article>
        <article>
          <span>Kaynak → yayın sürümü</span>
          <strong className="versions">
            v{runs.data?.source_versions?.[kind] ?? "—"}
            <i>→</i>v{data.data?.snapshot.source_version ?? "—"}
          </strong>
          <small>Son güncel veri karşılaştırması</small>
        </article>
      </div>
      <article className="sync-panel">
        <div>
          <span className="eyebrow">SENKRONİZASYON</span>
          <h3>{kind === "RETAIL" ? "Bireysel krediler" : "Ticari krediler"}</h3>
          <p>
            Yeni veri doğrulandıktan sonra kredi ve ödeme planı birlikte
            yayınlanır.
          </p>
          {last && <Status status={last.status} />}
        </div>
        <div className="sync-actions">
          <button className="primary" onClick={start} disabled={busy}>
            {busy ? "Senkronize ediliyor…" : "Şimdi senkronize et ↗"}
          </button>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
            />{" "}
            Aynı sürümü yeniden işle
          </label>
        </div>
      </article>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {last?.status === "REJECTED" && (
        <div className="rejected">
          <b>Yeni veri yayınlanmadı.</b>
          <span>Önceki geçerli portföy korunuyor.</span>
          <button onClick={() => onIssues(last.id)}>
            Doğrulama detaylarını gör →
          </button>
        </div>
      )}
      <div className="section-heading history-heading">
        <h3>Son çalıştırmalar</h3>
        <span className="subtle">Her değişiklik izlenebilir</span>
      </div>
      {runs.error ? (
        <p role="alert">{runs.error.message}</p>
      ) : (
        <div className="simple-table">
          <table>
            <thead>
              <tr>
                <th>Başlangıç</th>
                <th>Kaynak</th>
                <th>Sürüm</th>
                <th>Durum</th>
                <th>Süre</th>
                <th>Detay</th>
              </tr>
            </thead>
            <tbody>
              {runs.data?.results.map((run) => (
                <tr key={run.id}>
                  <td>{new Date(run.created_at).toLocaleString("tr-TR")}</td>
                  <td>{run.trigger}</td>
                  <td>v{run.source_version}</td>
                  <td>
                    <Status status={run.status} />
                  </td>
                  <td>{(run.duration_ms / 1000).toFixed(2)} sn</td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => onIssues(run.id)}
                    >
                      İncele →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!runs.data?.results.length && (
            <p className="empty">
              Henüz senkronizasyon yok. İlk verinizi bankaya yükleyin.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
