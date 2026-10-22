import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";
import { DataView } from "./DataView";
import { request, RequestError } from "../../api";
import type { Page } from "../../types";

vi.mock("../../api", async (original) => ({
  ...(await original<typeof import("../../api")>()),
  request: vi.fn(),
}));
const clients: QueryClient[] = [];
const session = { access: "test", tenant: "BANK001", username: "demo" };
const key = ["data", "BANK001", "RETAIL", "credit"];
function page(prefix: string, next: string | null = null, count = 1): Page {
  return {
    results: Array.from({ length: count }, (_, i) => ({
      loan_account_number: `${prefix}-${i}`,
    })),
    next_cursor: next,
    snapshot: {
      batch_id: prefix,
      source_version: prefix === "new" ? 2 : 1,
      published_at: "2026-10-22",
      row_count: count,
      row_counts: { credit: count },
    },
  };
}
function client() {
  const value = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  clients.push(value);
  return value;
}
function mount(value: QueryClient) {
  render(
    <QueryClientProvider client={value}>
      <DataView session={session} kind="RETAIL" />
    </QueryClientProvider>,
  );
}
afterEach(() => {
  cleanup();
  clients.splice(0).forEach((client) => client.clear());
  vi.resetAllMocks();
});

test("a stale cursor can restart on the new snapshot without retaining old rows", async () => {
  const cache = client();
  const otherTenant = ["data", "BANK002", "RETAIL", "credit"];
  cache.setQueryData(otherTenant, { marker: "preserve" });
  vi.mocked(request)
    .mockResolvedValueOnce(page("old", "old-cursor"))
    .mockRejectedValueOnce(new RequestError("Snapshot changed", 400))
    .mockResolvedValueOnce(page("new"));
  mount(cache);
  await screen.findByText("old-0");
  fireEvent.click(screen.getByRole("button", { name: "Sonraki 100 kayıt ↓" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Snapshot changed",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "İlk sayfadan yeniden yükle" }),
  );
  await screen.findByText("new-0");
  expect(screen.queryByText("old-0")).toBeNull();
  expect(vi.mocked(request).mock.calls.map(([url]) => url)).toEqual([
    "/api/data?loan_type=RETAIL&dataset=credit&limit=100&cursor=",
    "/api/data?loan_type=RETAIL&dataset=credit&limit=100&cursor=old-cursor",
    "/api/data?loan_type=RETAIL&dataset=credit&limit=100&cursor=",
  ]);
  expect(cache.getQueryData(otherTenant)).toEqual({ marker: "preserve" });
});

test("switching cached datasets resets the real viewport as well as virtual rows", async () => {
  const cache = client();
  cache.setQueryData(key, {
    pages: [page("credit", null, 100)],
    pageParams: [""],
  });
  cache.setQueryData(["data", "BANK001", "RETAIL", "payment_plan"], {
    pages: [page("plan", null, 100)],
    pageParams: [""],
  });
  mount(cache);
  const viewport = screen.getByRole("table").parentElement!;
  fireEvent.scroll(viewport, { target: { scrollTop: 2000 } });
  await waitFor(() => expect(screen.queryByText("credit-0")).toBeNull());
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Ödeme planları" }));
  });
  expect(screen.getByRole("table").parentElement!.scrollTop).toBe(0);
  expect(screen.getByText("plan-0")).toBeTruthy();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Krediler" }));
  });
  expect(screen.getByRole("table").parentElement!.scrollTop).toBe(0);
  expect(screen.getByText("credit-0")).toBeTruthy();
  expect(request).not.toHaveBeenCalled();
});
