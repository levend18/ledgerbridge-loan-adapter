import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Dataset, Kind, Session } from "../../types";
export function BankPortal({
  session,
  kind,
}: {
  session: Session;
  kind: Kind;
}) {
  const [dataset, setDataset] = useState<Dataset>("credit");
  const [method, setMethod] = useState("PUT");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const cache = useQueryClient();
  const base = `/bank/v1/tenants/${session.tenant}/loans/${kind}`;
  const key = `demo-${session.tenant.toLowerCase()}-key`;
  const meta = useQuery({
    queryKey: ["bank", session.tenant, kind],
    queryFn: async () => {
      const result = await fetch(`${base}/meta`, {
        headers: { "X-Bank-Key": key },
      });
      if (!result.ok) throw new Error("Banka bağlantısı kurulamadı");
      return result.json() as Promise<{
        version: number;
        datasets: Record<string, { row_count: number }>;
      }>;
    },
  });
  function upload() {
    if (!file) return;
    setMessage("");
    setProgress(0);
    const xhr = new XMLHttpRequest();
    xhr.open(method, `${base}/${dataset}`);
    xhr.setRequestHeader("X-Bank-Key", key);
    xhr.setRequestHeader("Content-Type", "text/csv");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable)
        setProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      setProgress(null);
      if (xhr.status >= 200 && xhr.status < 300) {
        setMessage("Dosya bankaya yüklendi. Yeni sürüm senkronizasyona hazır.");
        cache.invalidateQueries({ queryKey: ["bank", session.tenant, kind] });
        cache.invalidateQueries({ queryKey: ["runs", session.tenant] });
      } else setMessage(`Yükleme başarısız: ${xhr.responseText}`);
    };
    xhr.onerror = () => {
      setProgress(null);
      setMessage("Bağlantı kesildi. Yeniden deneyin.");
    };
    xhr.send(file);
  }
  return (
    <section>
      <div className="section-heading">
        <div>
          <h2>Banka portalı</h2>
          <p>Bankanın ham veri kaynağını güncelleyin.</p>
        </div>
        <span className="pill">DEMO BANKA SİMÜLASYONU</span>
      </div>
      <div className="portal-grid">
        <article className="panel">
          <h3>Dosya yükle</h3>
          <div className="form-row">
            <label>
              Veri seti
              <select
                value={dataset}
                onChange={(e) => setDataset(e.target.value as Dataset)}
              >
                <option value="credit">Kredi verisi</option>
                <option value="payment_plan">Ödeme planı</option>
              </select>
            </label>
            <label>
              Yükleme şekli
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value)}
              >
                <option value="PUT">Tam değiştirme (replace)</option>
                <option value="PATCH">Kısmi güncelleme (upsert)</option>
              </select>
            </label>
          </div>
          <label className="file-drop">
            <span className="upload-icon">↑</span>
            <b>{file ? file.name : "CSV dosyanızı seçin"}</b>
            <span>Noktalı virgülle ayrılmış UTF-8 · En fazla 250 MB</span>
            <input
              aria-label="CSV dosyası"
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </label>
          {progress !== null && (
            <progress
              value={progress}
              max={100}
              aria-label="Yükleme ilerlemesi"
            />
          )}
          <button
            className="primary"
            disabled={!file || progress !== null}
            onClick={upload}
          >
            {progress === null
              ? "Bankaya yükle →"
              : `Yükleniyor · %${progress}`}
          </button>
          {message && (
            <p role="status" className="notice">
              {message}
            </p>
          )}
        </article>
        <aside className="panel bank-summary">
          <span className="eyebrow">KAYNAK DURUMU</span>
          <h3>{session.tenant}</h3>
          <div className="big-number">v{meta.data?.version ?? "—"}</div>
          <p>Bankadaki güncel sürüm</p>
          <dl>
            {Object.entries(meta.data?.datasets || {}).map(([name, info]) => (
              <div key={name}>
                <dt>{name === "credit" ? "Kredi" : "Ödeme planı"}</dt>
                <dd>{info.row_count.toLocaleString("tr-TR")} kayıt</dd>
              </div>
            ))}
          </dl>
          <p className="subtle">
            Kredi ve ödeme planını yükledikten sonra Senkronizasyon ekranından
            durumu izleyebilirsiniz. Ham değerler bankada değiştirilmez.
          </p>
          {meta.error && <p role="alert">{meta.error.message}</p>}
        </aside>
      </div>
    </section>
  );
}
