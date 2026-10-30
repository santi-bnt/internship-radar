import { describe, expect, it } from "vitest";
import { splitScreenBounds } from "../lib/split-screen";

describe("split-screen application workspace", () => {
  it("places the portal and assistant on adjacent halves of the available display", () => {
    const { portal, assistant } = splitScreenBounds({ availWidth: 1921, availHeight: 1040, availLeft: -1921, availTop: 40 });
    expect(portal).toEqual({ left: -1921, top: 40, width: 960, height: 1040 });
    expect(assistant).toEqual({ left: -961, top: 40, width: 961, height: 1040 });
    expect(portal.left + portal.width).toBe(assistant.left);
    expect(assistant.left + assistant.width).toBe(0);
  });

  it("rejects a screen too small to show two usable windows", () => {
    expect(() => splitScreenBounds({ availWidth: 600, availHeight: 900 })).toThrow("Amplía");
  });
});
