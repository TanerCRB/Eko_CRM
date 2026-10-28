import { screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { mount } from "../src/mount";

describe("mount (what the entry src/main.tsx runs)", () => {
  let unmount: (() => void) | undefined;

  afterEach(() => {
    act(() => unmount?.());
    unmount = undefined;
    document.body.innerHTML = "";
  });

  it("renders the app into the page's root element", () => {
    document.body.innerHTML = '<div id="root"></div>';
    act(() => {
      unmount = mount(document);
    });
    const root = document.getElementById("root");
    expect(root).toContainElement(screen.getByRole("heading", { level: 1, name: "Pulpit" }));
  });

  it("fails loudly, naming the element, when the page has no root element", () => {
    document.body.innerHTML = '<div id="app"></div>';
    expect(() => mount(document)).toThrow('No element with id "root"');
  });
});
