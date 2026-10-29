// @vitest-environment node
import { ESLint } from "eslint";
import { beforeAll, describe, expect, it } from "vitest";

// EKO-1-10 K-04: a Date in a string is judged by type, so the proof is the type-aware rule's own
// finding under the real eslint.config.js. Fixture code exists only in memory, linted as the
// content of a real file under src/ so the project service types it with the tsconfig src/ uses.
const FIXTURE_PATH = "src/components/AppShell.tsx";
const TEMPLATE_RULE = "@typescript-eslint/restrict-template-expressions";
const CONCATENATION_RULE = "@typescript-eslint/restrict-plus-operands";

let eslint: ESLint;

beforeAll(() => {
  eslint = new ESLint();
});

async function ruleIds(code: string): Promise<(string | null)[]> {
  const results = await eslint.lintText(code, { filePath: FIXTURE_PATH });
  expect(results).toHaveLength(1);
  return results.flatMap((result) => result.messages.map((message) => message.ruleId));
}

const reached = {
  "a parameter": (type: string, embed: (value: string) => string) =>
    `export function label(visitDate: ${type}): string {\n  return ${embed("visitDate")};\n}\n`,
  "a variable": (type: string, embed: (value: string) => string) =>
    `export function label(input: ${type}): string {\n  const visitDate = input;\n  return ${embed("visitDate")};\n}\n`,
  "a function return": (type: string, embed: (value: string) => string) =>
    `export function label(next: () => ${type}): string {\n  return ${embed("next()")};\n}\n`,
  "an object property": (type: string, embed: (value: string) => string) =>
    `export function label(visit: { when: ${type} }): string {\n  return ${embed("visit.when")};\n}\n`,
};

const template = (value: string) => "`Visit: ${" + value + "}`";
const concatenation = (value: string) => `"Visit: " + ${value}`;

const TYPE_AWARE_LINT = { timeout: 120_000 };

describe("K-04: a Date-typed value in a string is a lint finding of the type rule", TYPE_AWARE_LINT, () => {
  describe.each(Object.entries(reached))("reached through %s", (_how, fixture) => {
    it("template literal: a Date is reported by restrict-template-expressions", async () => {
      expect(await ruleIds(fixture("Date", template))).toEqual([TEMPLATE_RULE]);
    });

    it("template literal: the same expression holding a string is no finding", async () => {
      expect(await ruleIds(fixture("string", template))).toEqual([]);
    });

    it("concatenation: a Date is reported by restrict-plus-operands", async () => {
      expect(await ruleIds(fixture("Date", concatenation))).toEqual([CONCATENATION_RULE]);
    });

    it("concatenation: the same expression holding a string is no finding", async () => {
      expect(await ruleIds(fixture("string", concatenation))).toEqual([]);
    });
  });
});
