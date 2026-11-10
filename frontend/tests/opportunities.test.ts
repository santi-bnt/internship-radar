import { describe, expect, it } from "vitest";
import { countryGroup, emptyOpportunity, filterOpportunities, Opportunity, safeWebsite } from "../lib/opportunities";

const make = (changes: Partial<Opportunity>): Opportunity => ({...emptyOpportunity, id: 1, program: "Robotics SURF", organization: "Purdue", fit_score: 80, fit_reasons: [], created_at: "2026-10-01", updated_at: "2026-11-01", ...changes});
const values = [make({country: "United States", notes: "International J1", research_areas: ["Robotics"], deadline: "2026-12-15", priority: "Very High", funding: ["Stipend"]}), make({id: 2, program: "McGill SURE", organization: "McGill", country: "Canada", fit_score: 70, professor: "Professor Montréal", deadline: null, priority: "High", favorite: true}), make({id: 3, program: "EPFL E3", organization: "EPFL", country: "Switzerland", fit_score: 90, research_areas: ["Robotics"], deadline: "2026-11-01", status: "Applying"})];

describe("saved opportunity search", () => {
  it("shows uncalibrated partial compatibility without a fabricated numerical score", () => {
    const role = make({id: 4, program: "AI / AIOps Engineer", organization: "Cognizant", country: "Mexico", status: "Recruiter Contacted", employment_type: "Full Time", compatibility_level: "Partial", fit_score: null});
    expect(filterOpportunities([...values, role], "", {}, "Best Match").at(-1)?.id).toBe(4);
    expect(filterOpportunities([role], "Cognizant", {status: "Recruiter Contacted"}, "Best Match")[0].fit_score).toBeNull();
  });
  it("searches notes, professor, location and areas with case/accent normalization", () => {
    expect(filterOpportunities(values, "j1 robotics", {}, "Best Match").map(o => o.id)).toEqual([1]);
    expect(filterOpportunities(values, "MONTREAL", {}, "Best Match").map(o => o.id)).toEqual([2]);
    expect(filterOpportunities(values, "switzerland", {}, "Best Match").map(o => o.id)).toEqual([3]);
  });
  it("combines filters across categories and preserves the full input list", () => {
    expect(filterOpportunities(values, "", {country: "United States", funding: "Stipend", research_areas: "Robotics"}, "Best Match").map(o => o.id)).toEqual([1]);
    expect(filterOpportunities(values, "", {country: "Europe", status: "Applying"}, "Best Match").map(o => o.id)).toEqual([3]);
    expect(filterOpportunities(values, "", {favorite: "yes"}, "Best Match").map(o => o.id)).toEqual([2]);
    expect(values.map(o => o.id)).toEqual([1, 2, 3]);
  });
  it("sorts deadlines with unknown dates last, and sorts by priority and fit", () => {
    expect(filterOpportunities(values, "", {}, "Deadline").map(o => o.id)).toEqual([3, 1, 2]);
    expect(filterOpportunities(values, "", {}, "Priority")[0].id).toBe(1);
    expect(filterOpportunities(values, "", {}, "Best Match").map(o => o.id)).toEqual([3, 1, 2]);
  });
  it("sorts recency and university without altering stored values", () => {
    const rows = [make({id: 1, organization: "Z", created_at: "2026-01-01", updated_at: "2026-10-01"}), make({id: 2, organization: "A", created_at: "2026-06-01", updated_at: "2026-11-01"})];
    for (const sort of ["Recently Added", "Recently Updated", "University"]) expect(filterOpportunities(rows, "", {}, sort)[0].id).toBe(2);
  });
  it("classifies geography and rejects unsafe website links", () => {
    expect(countryGroup("USA")).toBe("United States");
    expect(countryGroup("Switzerland")).toBe("Europe");
    expect(countryGroup("Mexico")).toBe("Other");
    expect(safeWebsite("javascript:alert(1)")).toBeUndefined();
    expect(safeWebsite("https://eee.epfl.ch/")).toBe("https://eee.epfl.ch/");
  });
});
