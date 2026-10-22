import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { label, request } from "../../api";
import type { Dataset, Kind, Profile, Session, Stats } from "../../types";
echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);
function Distribution({ stats }: { stats: Stats }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption({
      animation: false,
      grid: { left: 70, right: 16, top: 8, bottom: 25 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "value", axisLabel: { color: "#6d7e80" } },
      yAxis: {
        type: "category",
        data: stats.top?.map((p) => p.value),
        axisLabel: { color: "#456064" },
      },
      series: [
        {
          type: "bar",
          data: stats.top?.map((p) => p.count),
          itemStyle: { color: "#279184", borderRadius: [0, 4, 4, 0] },
          barMaxWidth: 18,
        },
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [stats]);
  return (
    <div
      ref={ref}
      className="chart"
      role="img"
      aria-label="Kategori dağılımı"
    />
  );
}
export function ProfileView({
  session,
  kind,
}: {
  session: Session;
  kind: Kind;
}) {
  const [dataset, setDataset] = useState<Dataset>("credit");
  const query = useQuery({
    queryKey: ["profiles", session.tenant, kind],
    queryFn: () =>
      request<Profile>(`/api/profiling?loan_type=${kind}`, session),
    retry: false,
  });
  return (
    <section>
      <div className="section-heading">
        <div>
          <h2>Verinin içini görün</h2>
          <p>Yayındaki snapshot için kolon kalitesi ve dağılımlar.</p>
        </div>
        <select
          aria-label="Profil veri seti"
          value={dataset}
          onChange={(e) => setDataset(e.target.value as Dataset)}
        >
          <option value="credit">Krediler</option>
          <option value="payment_plan">Ödeme planları</option>
        </select>
      </div>
      {query.isPending ? (
        <p>Profiller yükleniyor…</p>
      ) : query.error ? (
        <p role="alert" className="notice">
          {query.error.message}
        </p>
      ) : (
        <div className="profile-grid">
          {Object.entries(query.data.datasets[dataset]).map(([name, stats]) => (
            <article className="profile-card" key={name}>
              <h3>{label(name)}</h3>
              <div className="null-line">
                <span>Boş değer</span>
                <b>%{(stats.null_ratio * 100).toFixed(1)}</b>
              </div>
              <div className="meter">
                <i style={{ width: `${stats.null_ratio * 100}%` }} />
              </div>
              {"mean" in stats ? (
                <dl>
                  <div>
                    <dt>Minimum</dt>
                    <dd>{stats.min ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>Maksimum</dt>
                    <dd>{stats.max ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>Ortalama</dt>
                    <dd>
                      {stats.mean?.toLocaleString("tr-TR", {
                        maximumFractionDigits: 6,
                      }) ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>Standart sapma</dt>
                    <dd>
                      {stats.stddev?.toLocaleString("tr-TR", {
                        maximumFractionDigits: 6,
                      }) ?? "—"}
                    </dd>
                  </div>
                </dl>
              ) : stats.top ? (
                <>
                  <p className="subtle">
                    {stats.high_cardinality
                      ? "Yüksek çeşitlilik · özet sınırını aşıyor"
                      : `${stats.distinct_count} farklı değer · En sık: ${stats.most_frequent ?? "—"}`}
                  </p>
                  {stats.top.length > 0 && <Distribution stats={stats} />}
                </>
              ) : (
                <dl>
                  <div>
                    <dt>İlk tarih</dt>
                    <dd>{stats.min ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>Son tarih</dt>
                    <dd>{stats.max ?? "—"}</dd>
                  </div>
                </dl>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
