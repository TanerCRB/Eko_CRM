import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/mount", () => ({ mount: vi.fn() }));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("K-06: bounded lazy-module recovery", () => {
  it("allows one automatic navigation and leaves a second failure observable", async () => {
    const listeners: Array<(event: Event) => void> = [];
    const location = { search: "", assign: vi.fn() };
    vi.stubGlobal("window", {
      location,
      addEventListener: (type: string, listener: (event: Event) => void) => {
        if (type === "vite:preloadError") {
          listeners.push(listener);
        }
      },
    });
    await import("../src/main");
    const [recover] = listeners;
    if (!recover) {
      throw new Error("The entrypoint did not register lazy-module recovery");
    }

    const firstFailure = new Event("vite:preloadError", { cancelable: true });
    recover(firstFailure);

    expect(firstFailure.defaultPrevented).toBe(true);

    location.search = "?recovery=1";
    const secondFailure = new Event("vite:preloadError", { cancelable: true });
    recover(secondFailure);

    expect(secondFailure.defaultPrevented).toBe(false);
    expect(location.assign).toHaveBeenCalledTimes(1);
    expect(location.assign).toHaveBeenCalledExactlyOnceWith("/klienci?recovery=1");
  });
});
