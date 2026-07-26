import { describe, expect, it } from "vitest";
import {
  STORAGE_KEY,
  loadSubmissions,
  removeSubmission,
  saveSubmissions,
  upsertSubmission,
  type StoredSubmission,
} from "./storage";

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

const first: StoredSubmission = {
  submissionId: "submission-123",
  jobId: null,
  base: "http://localhost:8000",
  fileName: "song.wav",
  submittedAt: "2026-07-26T00:00:00.000Z",
};

describe("submission storage", () => {
  it("round-trips browser-owned submission references", () => {
    const storage = new MemoryStorage();

    saveSubmissions(storage, [first]);

    expect(loadSubmissions(storage)).toEqual([first]);
  });

  it("treats corrupted or invalid data as empty", () => {
    const storage = new MemoryStorage();
    storage.setItem(STORAGE_KEY, "{");
    expect(loadSubmissions(storage)).toEqual([]);

    storage.setItem(STORAGE_KEY, JSON.stringify([{ submissionId: 42 }]));
    expect(loadSubmissions(storage)).toEqual([]);
  });

  it("upserts a returned Job ID without duplicating the submission", () => {
    const storage = new MemoryStorage();
    saveSubmissions(storage, [first]);

    const updated = upsertSubmission(storage, {
      ...first,
      jobId: "job123",
    });

    expect(updated).toEqual([{ ...first, jobId: "job123" }]);
    expect(loadSubmissions(storage)).toEqual(updated);
  });

  it("removes only the selected browser-owned submission", () => {
    const storage = new MemoryStorage();
    const second = {
      ...first,
      submissionId: "submission-456",
      jobId: "job456",
    };
    saveSubmissions(storage, [first, second]);

    expect(removeSubmission(storage, first.submissionId)).toEqual([second]);
    expect(loadSubmissions(storage)).toEqual([second]);
  });
});
