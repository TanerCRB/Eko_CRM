// Deliberately failing test: shows the frontend CI job turns a PR red (EKO-1-06, K-05). Never merged.
import { expect, test } from "vitest";

test("ci red probe fails on purpose", () => {
  expect(1).toBe(2);
});
