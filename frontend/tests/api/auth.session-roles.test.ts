// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { readSession } from "../../src/api/auth";
import { SESSION_URL, stubFetch } from "../support/http";

// EKO-3-08 K-07 (and K-04's SPA half): the session read's roles reach the SPA, read only from the
// answer; they decide what is shown, never what the server allows. Synthetic values (ADR-0005).

function answer(body: unknown) {
  stubFetch({ [SESSION_URL]: [{ status: 200, raw: JSON.stringify(body) }] });
}

const SUBJECT = "synthetic-subject-0001";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EKO-3-08 K-07: the session read carries the caller's roles", () => {
  it("the roles the server answered are the session's roles", async () => {
    answer({ subject: SUBJECT, name: "Anna Testowa", roles: ["manager", "rep"] });

    await expect(readSession()).resolves.toEqual({
      kind: "authenticated",
      session: { subject: SUBJECT, name: "Anna Testowa", roles: ["manager", "rep"] },
    });
  });

  it("contrast: a rep's answer holds no manager", async () => {
    answer({ subject: SUBJECT, name: "Anna Testowa", roles: ["rep"] });

    await expect(readSession()).resolves.toEqual({
      kind: "authenticated",
      session: { subject: SUBJECT, name: "Anna Testowa", roles: ["rep"] },
    });
  });

  it("edge: an answer without roles (older backend) is a session with no roles", async () => {
    answer({ subject: SUBJECT, name: "Anna Testowa" });

    await expect(readSession()).resolves.toEqual({
      kind: "authenticated",
      session: { subject: SUBJECT, name: "Anna Testowa", roles: [] },
    });
  });

  it("A-13: a role name the SPA does not know is left out, the known ones kept", async () => {
    answer({ subject: SUBJECT, name: null, roles: ["auditor", "manager"] });

    await expect(readSession()).resolves.toEqual({
      kind: "authenticated",
      session: { subject: SUBJECT, name: null, roles: ["manager"] },
    });
  });

  it("A-14: roles that are not a list of strings make the answer invalid", async () => {
    for (const roles of ["manager", { manager: true }, [1], null]) {
      answer({ subject: SUBJECT, name: null, roles });

      await expect(readSession()).resolves.toEqual({ kind: "invalid" });
    }
  });
});
