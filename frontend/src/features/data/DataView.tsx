import { useMemo, useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { label, request } from "../../api";
import type { Dataset, Kind, Page, Row, Session } from "../../types";
export function DataView({ session, kind }: { session: Session; kind: Kind }) {
  const [dataset, setDataset] = useState<Dataset>("credit");
  const [scroll, setScroll] = useState(0);
  const cache = useQueryClient();
  const queryKey = ["data", session.tenant, kind, dataset];
  const query = useInfiniteQuery({
    queryKey,
    initialPageParam: "",
    queryFn: ({ pageParam }) =>
      request<Page>(
        `/api/data?loan_type=${kind}&dataset=${dataset}&limit=100&cursor=${encodeURIComponent(pageParam)}`,
        session,
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
    retry: false,
  });
  const rows = useMemo(
    () => query.data?.pages.flatMap((p) => p.results) || [],
    [query.data],
  );
  const columns = useMemo(
    () =>
      Object.keys(rows[0] || {})
        .filter(
          (k) => !["tenant_id", "batch_id", "source_row_number"].includes(k),
        )
        .map((key) => ({
          accessorKey: key,
          header: label(key),
          cell: ({ getValue }: { getValue: () => unknown }) =>
            String(getValue() ?? "—"),
        })),
    [rows],
  );
  const table = useReactTable<Row>({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });
  const first = Math.max(0, Math.floor(scroll / 40) - 5);
  const visible = table.getRowModel().rows.slice(first, first + 25);
  return (
    <section>
      <div className="section-heading">
        <div>
          <h2>Portföy kayıtları</h2>
          <p>Yayındaki veriyi kredi ve ödeme planı bazında inceleyin.</p>
        </div>
        <div className="segmented">
          <button
            className={dataset === "credit" ? "selected" : ""}
            onClick={() => {
              setDataset("credit");
              setScroll(0);
            }}
          >
            Krediler
          </button>
          <button
            className={dataset === "payment_plan" ? "selected" : ""}
            onClick={() => {
              setDataset("payment_plan");
              setScroll(0);
            }}
          >
            Ödeme planları
          </button>
        </div>
      </div>
      {query.isPending ? (
        <p>Veriler yükleniyor…</p>
      ) : query.error ? (
        <div role="alert" className="notice">
          <p>{query.error.message}</p>
          <button
            onClick={() => {
              setScroll(0);
              void cache.resetQueries({ queryKey, exact: true });
            }}
          >
            İlk sayfadan yeniden yükle
          </button>
        </div>
      ) : (
        <>
          <div className="table-meta">
            <span>
              <b>
                {query.data?.pages[0].snapshot.row_count.toLocaleString(
                  "tr-TR",
                )}
              </b>{" "}
              kayıt
            </span>
            <span>
              Sürüm {query.data?.pages[0].snapshot.source_version} · Güncel
              snapshot
            </span>
          </div>
          <div
            key={dataset}
            className="data-viewport"
            onScroll={(e) => setScroll(e.currentTarget.scrollTop)}
          >
            <div role="table" style={{ minWidth: columns.length * 170 }}>
              <div
                role="row"
                className="grid-header"
                style={{
                  gridTemplateColumns: `repeat(${columns.length},170px)`,
                }}
              >
                {table.getHeaderGroups()[0]?.headers.map((h) => (
                  <div role="columnheader" key={h.id}>
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </div>
                ))}
              </div>
              <div style={{ height: rows.length * 40, position: "relative" }}>
                {visible.map((row, i) => (
                  <div
                    role="row"
                    className="grid-row"
                    key={row.id}
                    style={{
                      top: (first + i) * 40,
                      gridTemplateColumns: `repeat(${columns.length},170px)`,
                    }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <div role="cell" key={cell.id}>
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="table-footer">
            <span>{rows.length} kayıt yüklendi</span>
            <button
              disabled={!query.hasNextPage || query.isFetchingNextPage}
              onClick={() => query.fetchNextPage()}
            >
              {query.isFetchingNextPage ? "Yükleniyor…" : "Sonraki 100 kayıt ↓"}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
