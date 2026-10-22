import { useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { request } from "../../api";
import { Status } from "../sync/SyncView";
import type { Kind, Row, Run, Session } from "../../types";
export function IssuesView({
  session,
  kind,
  runId,
}: {
  session: Session;
  kind: Kind;
  runId: string;
}) {
  const [severity, setSeverity] = useState("");
  const runs = useQuery({
    queryKey: ["runs", session.tenant, kind],
    queryFn: () =>
      request<{ results: Run[] }>(`/api/runs?loan_type=${kind}`, session),
  });
  const [selected, setSelected] = useState(runId);
  const id = selected || runs.data?.results[0]?.id || "";
  const run = useQuery({
    queryKey: ["run", session.tenant, id],
    queryFn: () => request<Run>(`/api/sync/${id}`, session),
    enabled: !!id,
  });
  const issues = useInfiniteQuery({
    queryKey: ["issues", session.tenant, id, severity],
    enabled: !!id,
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      request<{ results: Row[]; next_cursor: number | null }>(
        `/api/validation-issues?sync_run_id=${id}&cursor=${pageParam}&limit=100${severity ? `&severity=${severity}` : ""}`,
        session,
      ),
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  const counts = run.data?.issues_summary || {};
  const totals = (type: string) =>
    Object.entries(counts)
      .filter(([key]) => key.startsWith(type + ":"))
      .reduce((sum, [, count]) => sum + count, 0);
  return (
    <section>
      <div className="section-heading">
        <div>
          <h2>Doğrulama merkezi</h2>
          <p>Ham değer, normalleştirilmiş sonuç ve kararın nedeni.</p>
        </div>
        <select
          aria-label="Çalıştırma"
          value={id}
          onChange={(e) => setSelected(e.target.value)}
        >
          {runs.data?.results.map((r) => (
            <option key={r.id} value={r.id}>
              {new Date(r.created_at).toLocaleString("tr-TR")} · {r.status}
            </option>
          ))}
        </select>
      </div>
      {run.data && (
        <div className={run.data.status === "REJECTED" ? "rejected" : "notice"}>
          <Status status={run.data.status} />
          <span>
            {run.data.status === "REJECTED"
              ? "Yeni veri reddedildi. Son geçerli portföy korunuyor."
              : "Bu çalıştırmaya ait doğrulama sonuçları."}
          </span>
        </div>
      )}
      <div className="kpi-grid issue-kpis">
        {["ERROR", "WARNING", "CORRECTED"].map((type) => (
          <article key={type}>
            <span>{type}</span>
            <strong>{totals(type).toLocaleString("tr-TR")}</strong>
            <small>
              {type === "ERROR"
                ? "Yayını engelleyen hata"
                : type === "WARNING"
                  ? "İncelenmesi önerilen değer"
                  : "Normalize edilen değer"}
            </small>
          </article>
        ))}
      </div>
      <div className="rule-list">
        {Object.entries(counts).map(([rule, count]) => (
          <span className="rule" key={rule}>
            {rule} <b>{count.toLocaleString("tr-TR")}</b>
          </span>
        ))}
      </div>
      <div className="section-heading">
        <h3>Satır detayları</h3>
        <select
          aria-label="Önem derecesi"
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
        >
          <option value="">Tüm seviyeler</option>
          {["ERROR", "WARNING", "CORRECTED"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </div>
      <div className="simple-table">
        <table>
          <thead>
            <tr>
              {[
                "Satır",
                "Kredi",
                "Kolon",
                "Kural",
                "Seviye",
                "Ham değer",
                "Sonuç",
              ].map((s) => (
                <th key={s}>{s}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {issues.data?.pages
              .flatMap((p) => p.results)
              .map((row) => (
                <tr key={String(row.id)}>
                  {[
                    "row_number",
                    "key",
                    "column",
                    "rule_id",
                    "severity",
                    "raw_value",
                    "normalized_value",
                  ].map((k) => (
                    <td key={k}>{String(row[k] ?? "—")}</td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
        {!issues.data?.pages[0].results.length && (
          <p className="empty">Gösterilecek doğrulama detayı yok.</p>
        )}
      </div>
      <div className="table-footer">
        <span>İlk 1.000 detay saklanır; sayaçlar tüm veriyi kapsar.</span>
        <button
          disabled={!issues.hasNextPage || issues.isFetchingNextPage}
          onClick={() => issues.fetchNextPage()}
        >
          Daha fazla göster ↓
        </button>
      </div>
      {issues.error && <p role="alert">{issues.error.message}</p>}
    </section>
  );
}
