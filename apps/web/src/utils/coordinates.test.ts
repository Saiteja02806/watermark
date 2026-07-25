import { describe, expect, it } from "vitest";
import { clientToCanvas, formatTime, frameToTime } from "./coordinates";

describe("coordinate mapping", () => {
  it("maps a resized canvas back to processing pixels", () => {
    const point = clientToCanvas(
      460,
      290,
      { left: 100, top: 50, width: 720, height: 480 },
      360,
      240,
    );
    expect(point).toEqual({ x: 180, y: 120 });
  });

  it("clamps pointer positions to the frame", () => {
    const point = clientToCanvas(
      -10,
      900,
      { left: 0, top: 0, width: 200, height: 100 },
      400,
      200,
    );
    expect(point).toEqual({ x: 0, y: 200 });
  });
});

describe("timeline helpers", () => {
  it("converts frames and formats short durations", () => {
    expect(frameToTime(45, 30)).toBe(1.5);
    expect(formatTime(61.25)).toBe("1:01.25");
  });
});

