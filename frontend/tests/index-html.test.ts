import { describe, expect, it } from "vitest";
import html from "../index.html?raw";

// K-01 asserts the built page served through `proxy` carries this root element and a hashed bundle.
describe("index.html (K-01: the SPA page served through proxy)", () => {
  const page = new DOMParser().parseFromString(html, "text/html");

  it("has exactly one root element the app mounts into", () => {
    expect(page.querySelectorAll("div#root")).toHaveLength(1);
  });

  it("loads the application entry as a module script, which Vite rewrites to a hashed asset", () => {
    const scripts = Array.from(page.querySelectorAll("script"));
    expect(scripts.map((s) => [s.type, s.getAttribute("src")])).toEqual([
      ["module", "/src/main.tsx"],
    ]);
  });
});
