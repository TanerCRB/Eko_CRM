import { readdirSync, readFileSync } from "node:fs";
import { extname, join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "../src/App";

const prohibited = {
  innerHTML: /innerHTML/i,
  prototypePersona: /persona/i,
  prototypeStore: /EkoFixtures|EkoDomain|window\.Eko|const STORAGE|let state\s*=/,
  prototypeImport: /docs\/prototype\/P2|prototype\/P2/,
} as const;

function findings(source: string): string[] {
  return Object.entries(prohibited)
    .filter(([, pattern]) => pattern.test(source))
    .map(([name]) => name);
}

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? sourceFiles(path) : [path];
  });
}

describe("K-05: production excludes prototype orchestration", () => {
  it("finds no prohibited mechanism or prototype import in production source", () => {
    const sourceRoot = join(process.cwd(), "src");
    const sources = sourceFiles(sourceRoot).filter((path) =>
      [".ts", ".tsx", ".js", ".jsx"].includes(extname(path)),
    );
    expect(sources.length).toBeGreaterThan(0);
    const violations = sources.flatMap((path) =>
      findings(readFileSync(path, "utf8")).map((finding) => `${path}: ${finding}`),
    );
    expect(violations).toEqual([]);
  });

  it("uses English lazy-component identifiers while preserving the emitted chunk name", () => {
    const appSource = readFileSync(join(process.cwd(), "src/App.tsx"), "utf8");
    const featureSource = readFileSync(join(process.cwd(), "src/features/Klienci.tsx"), "utf8");

    expect(appSource).toContain('const Customers = lazy(() => import("./features/Klienci"))');
    expect(appSource).toContain("<Customers />");
    expect(featureSource).toContain("export default function Customers()");
  });

  it.each([
    ["innerHTML", "element.innerHTML = supplied;"],
    ["innerHTML", "const props = { dangerouslySetInnerHTML: supplied };"],
    ["prototypePersona", "let persona = 'alex';"],
    ["prototypeStore", "let state = copy(window.EkoFixtures);"],
    ["prototypeImport", "import view from '../../docs/prototype/P2/src/app.js';"],
  ])("rejects a minimal fixture containing %s", (finding, fixture) => {
    expect(findings(fixture)).toContain(finding);
  });

  it("does not misclassify component-local visibility state as a global demo store", () => {
    expect(findings("function View() { const [open, setOpen] = useState(false); }")).toEqual([]);
  });

  it("renders no persona selector or demo reset control", () => {
    render(<App />);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /demo|demonstracj|persona|reset/i }),
    ).not.toBeInTheDocument();
    expect(document.querySelector("[data-persona]")).not.toBeInTheDocument();
  });
});
