import { describe, expect, it, vi } from "vitest";
import {
  formatBuildIdentity,
  logBuildIdentity,
  readBuildIdentity,
} from "./version";

const FULL_REVISION = "afa06994f35e97ce8fd1729f10d69958524ec634";

describe("runtime product version", () => {
  it("reads one product version and full revision from the build environment", () => {
    expect(
      readBuildIdentity({
        VITE_PRODUCT_VERSION: "v0.2.0",
        VITE_BUILD_REVISION: FULL_REVISION,
      }),
    ).toEqual({
      productVersion: "v0.2.0",
      revision: FULL_REVISION,
      shortRevision: "afa06994",
    });
  });

  it("uses deterministic local defaults when build metadata is absent", () => {
    expect(readBuildIdentity({})).toEqual({
      productVersion: "dev",
      revision: "unknown",
      shortRevision: "unknown",
    });
  });

  it("formats the exact console build identity", () => {
    const identity = readBuildIdentity({
      VITE_PRODUCT_VERSION: "v0.2.0",
      VITE_BUILD_REVISION: FULL_REVISION,
    });

    expect(formatBuildIdentity(identity)).toBe("[LMDJ] v0.2.0 · afa06994");
  });

  it("logs one complete identity per startup call", () => {
    const logger = vi.fn();
    const identity = readBuildIdentity({
      VITE_PRODUCT_VERSION: "v0.2.0",
      VITE_BUILD_REVISION: FULL_REVISION,
    });

    logBuildIdentity(identity, logger);

    expect(logger).toHaveBeenCalledOnce();
    expect(logger).toHaveBeenCalledWith("[LMDJ] v0.2.0 · afa06994");
  });
});
