import { screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { pageNavigation } from "../src/api/navigation";
import { mount } from "../src/mount";
import { SESSION_URL, signedIn, stubFetch } from "./support/http";

describe("mount (what the entry src/main.tsx runs)", () => {
  let unmount: (() => void) | undefined;

  afterEach(() => {
    act(() => unmount?.());
    unmount = undefined;
    document.body.innerHTML = "";
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders the app into the page's root element", async () => {
    // EKO-2-01 H6-F A: the shell renders only behind a valid session.
    stubFetch({ [SESSION_URL]: [signedIn("Anna Testowa")] });
    vi.spyOn(pageNavigation, "assign").mockImplementation(() => undefined);
    document.body.innerHTML = '<div id="root"></div>';
    act(() => {
      unmount = mount(document);
    });
    const root = document.getElementById("root");
    expect(root).toContainElement(await screen.findByRole("heading", { level: 1, name: "Pulpit" }));
  });

  it("fails loudly, naming the element, when the page has no root element", () => {
    document.body.innerHTML = '<div id="app"></div>';
    expect(() => mount(document)).toThrow('No element with id "root"');
  });
});
