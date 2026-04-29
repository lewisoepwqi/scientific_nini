import { describe, expect, it } from "vitest";
import { formatSessionRelativeTime, getSessionActivityIso } from "./session-list-time";
import type { SessionItem } from "../store/types";

describe("session-list-time", () => {
  it("uses last_message_at before updated_at and created_at", () => {
    const session: SessionItem = {
      id: "s1",
      title: "会话",
      message_count: 1,
      source: "disk",
      created_at: "2026-01-01T00:00:00+00:00",
      updated_at: "2026-01-02T00:00:00+00:00",
      last_message_at: "2026-01-03T00:00:00+00:00",
    };

    expect(getSessionActivityIso(session)).toBe("2026-01-03T00:00:00+00:00");
  });

  it("falls back to updated_at when last_message_at is absent", () => {
    const session: SessionItem = {
      id: "s2",
      title: "会话",
      message_count: 1,
      source: "disk",
      created_at: "2026-01-01T00:00:00+00:00",
      updated_at: "2026-01-02T00:00:00+00:00",
    };

    expect(getSessionActivityIso(session)).toBe("2026-01-02T00:00:00+00:00");
  });

  it("ignores polluted created_at that is newer than activity time", () => {
    const session: SessionItem = {
      id: "s3",
      title: "会话",
      message_count: 1,
      source: "disk",
      created_at: "2026-04-29T02:57:18+00:00",
      updated_at: "2026-04-28T18:57:07+00:00",
      last_message_at: "2026-04-28T18:57:07+00:00",
    };

    expect(getSessionActivityIso(session)).toBe("2026-04-28T18:57:07+00:00");
  });

  it("clamps future timestamps to current moment", () => {
    const now = Date.parse("2026-04-29T03:00:00+00:00");
    const future = "2026-04-29T03:05:00+00:00";

    expect(formatSessionRelativeTime(future, now)).toBe("此刻");
  });

  it("formats same-day activity as today after one hour", () => {
    const now = Date.parse("2026-04-29T12:00:00+00:00");
    const earlier = "2026-04-29T09:30:00+00:00";

    expect(formatSessionRelativeTime(earlier, now)).toBe("今天");
  });
});
