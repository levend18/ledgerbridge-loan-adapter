import {
  fireEvent,
  render,
  screen,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Login } from "./Login";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
test("successful login uses the tenant in the signed token response", async () => {
  const onLogin = vi.fn();
  const access = `header.${btoa(JSON.stringify({ tenant_id: "BANK002" }))}.signature`;
  const fetchMock = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({ access }) });
  vi.stubGlobal("fetch", fetchMock);
  render(<Login onLogin={onLogin} />);
  fireEvent.change(screen.getByLabelText("Kullanıcı adı"), {
    target: { value: "bank002_user" },
  });
  fireEvent.change(screen.getByLabelText("Şifre"), {
    target: { value: "demo1234" },
  });
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() =>
    expect(onLogin).toHaveBeenCalledWith({
      access,
      tenant: "BANK002",
      username: "bank002_user",
    }),
  );
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
    username: "bank002_user",
    password: "demo1234",
  });
});
test("failed login keeps the user on the form and explains the error", async () => {
  const onLogin = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Geçersiz kullanıcı veya şifre" }),
    }),
  );
  render(<Login onLogin={onLogin} />);
  fireEvent.change(screen.getByLabelText("Şifre"), {
    target: { value: "wrong" },
  });
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toContain("Geçersiz"),
  );
  expect(onLogin).not.toHaveBeenCalled();
});
