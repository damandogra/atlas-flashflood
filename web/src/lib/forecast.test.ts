// The browser forecast must give the same answer as pipeline/forecast/core.py.
// Fixture written by `python -m pytest tests/test_forecast.py`.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { assess } from "./forecast";
import type { Meta } from "./data";

const meta = JSON.parse(readFileSync(new URL("../../public/data/meta.json", import.meta.url), "utf8")) as Meta;
const cases = JSON.parse(readFileSync(new URL("./forecast.fixture.json", import.meta.url), "utf8")) as {
  time: string[]; rain: number[]; antecedent: number;
  expected: { p24_mm: number; amc: number; p24_equivalent_mm: number; scenario: string | null; peak_hour: string; library_t0: string };
}[];

describe("forecast parity with Python", () => {
  for (const [i, c] of cases.entries()) {
    it(`case ${i}`, () => {
      const a = assess(meta, c.time, c.rain, c.antecedent);
      expect(a.amc).toBe(c.expected.amc);
      expect(a.p24_mm).toBeCloseTo(c.expected.p24_mm, 1);
      expect(a.p24_equivalent_mm).toBeCloseTo(c.expected.p24_equivalent_mm, 1);
      expect(a.scenario).toBe(c.expected.scenario);
      expect(Date.parse(a.peak_hour)).toBe(Date.parse(c.expected.peak_hour));
      expect(Date.parse(a.library_t0)).toBe(Date.parse(c.expected.library_t0));
    });
  }
});
