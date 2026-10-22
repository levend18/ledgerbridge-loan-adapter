import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";
import { ProfileView } from "./ProfileView";

vi.mock("echarts/core", () => ({
  use: vi.fn(),
  init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }),
}));
vi.stubGlobal(
  "ResizeObserver",
  class {
    observe() {}
    disconnect() {}
  },
);
afterEach(cleanup);

test("high-cardinality profiles still show exact counts, mode and distribution", () => {
  const cache = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity } },
  });
  cache.setQueryData(["profiles", "BANK001", "RETAIL"], {
    datasets: {
      credit: {
        customer_id: {
          count: 1007,
          null_ratio: 0,
          high_cardinality: true,
          distinct_count: 1001,
          most_frequent: "CUST_000999",
          top: [{ value: "CUST_000999", count: 4 }],
        },
      },
      payment_plan: {},
    },
  });
  render(
    <QueryClientProvider client={cache}>
      <ProfileView
        session={{ access: "test", tenant: "BANK001", username: "demo" }}
        kind="RETAIL"
      />
    </QueryClientProvider>,
  );
  expect(
    screen.getByText("1001 farklı değer · En sık: CUST_000999"),
  ).toBeTruthy();
  expect(screen.getByRole("img", { name: "Kategori dağılımı" })).toBeTruthy();
  cleanup();
  cache.clear();
});
