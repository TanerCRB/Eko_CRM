// @vitest-environment node
import { describe, expect, it } from "vitest";
import { COUNTRY_CODES, countryName, countryOptions, DEFAULT_COUNTRY } from "../../src/api/countries";

// The list is a hand copy of the backend's closed list (G-3 A); its agreement with the OpenAPI
// document is the backend's contract check (EKO-1-35), so these checks hold only its shape.
describe("K-07 support: the form's country list", () => {
  it("holds 249 distinct two-letter codes, Poland among them as the default", () => {
    expect(COUNTRY_CODES).toHaveLength(249);
    expect(new Set(COUNTRY_CODES).size).toBe(COUNTRY_CODES.length);
    expect(COUNTRY_CODES.every((code) => /^[A-Z]{2}$/.test(code))).toBe(true);
    expect(DEFAULT_COUNTRY).toBe("PL");
    expect(COUNTRY_CODES).toContain(DEFAULT_COUNTRY);
  });

  it("names a code in Polish for display and shows an unknown code as it came", () => {
    expect(countryName("PL")).toBe("Polska");
    expect(countryName("DE")).toBe("Niemcy");
    expect(countryName("QQ")).toBe("QQ");
    expect(countryOptions().find((option) => option.code === "PL")?.name).toBe("Polska");
  });
});
