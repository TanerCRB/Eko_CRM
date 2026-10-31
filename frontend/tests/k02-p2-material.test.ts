// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const pairs = [
  ["tokens.css", "../src/styles/tokens.css", "../../docs/prototype/P2/styles/tokens.css"],
  ["mark.svg", "../src/assets/mark.svg", "../../docs/prototype/P2/assets/mark.svg"],
  ["field-lines.svg", "../src/assets/field-lines.svg", "../../docs/prototype/P2/assets/field-lines.svg"],
] as const;

describe("K-02: shipped P2 material remains byte-identical", () => {
  it.each(pairs)("%s matches its P2 source and detects a one-byte change", (name, shipped, source) => {
    const shippedBytes = readFileSync(new URL(shipped, import.meta.url));
    const sourceBytes = readFileSync(new URL(source, import.meta.url));
    expect(shippedBytes.equals(sourceBytes), `${name} differs from P2`).toBe(true);

    const changed = new Uint8Array(sourceBytes);
    changed[0] = (changed[0] ?? 0) ^ 1;
    expect(Buffer.from(changed).equals(sourceBytes)).toBe(false);
  });
});
