import {expect, test, vi} from "vitest";

import {WEB_RUNTIME_IDENTITY} from
  "../../../products/lmdj/generated/web-runtime-identity.mjs";
import {
  announceBuildIdentity,
  creatorBuildIdentity,
  describeBuildIdentity,
  shortBuildLabel,
} from "../src/runtime/build_identity";

const SOURCE = {
  product_build: "9.8.7.6",
  protocol_version: 1,
  platform: {version: "0.3.6"},
  hosts: {"creator-web": {id: "creator-web", version: "1.5.0"}},
};

test("derives the Creator build identity from the generated assembly identity", () => {
  const identity = creatorBuildIdentity(SOURCE);
  expect(identity).toEqual({
    productBuild: "9.8.7.6",
    hostId: "creator-web",
    hostVersion: "1.5.0",
    platformVersion: "0.3.6",
    protocolVersion: 1,
  });
  expect(Object.isFrozen(identity)).toBe(true);
});

test("labels the build for the status bar and the console", () => {
  const identity = creatorBuildIdentity(SOURCE);
  expect(shortBuildLabel(identity)).toBe("v9.8.7.6 · creator-web 1.5.0");
  expect(describeBuildIdentity(identity)).toBe(
    "Product Build 9.8.7.6 · creator-web 1.5.0 · web-runtime-platform 0.3.6 · protocol 1",
  );
});

test("announces the build identity once through console.info", () => {
  const identity = creatorBuildIdentity(SOURCE);
  const info = vi.fn();
  announceBuildIdentity(identity, {info});
  expect(info).toHaveBeenCalledTimes(1);
  expect(info.mock.calls[0]?.[0]).toBe(
    "LMDJ Creator Product Build 9.8.7.6 · creator-web 1.5.0 · web-runtime-platform 0.3.6 · protocol 1",
  );
  expect(info.mock.calls[0]?.[1]).toBe(identity);
});

test("the active Product Assembly identity produces a complete build identity", () => {
  const identity = creatorBuildIdentity(WEB_RUNTIME_IDENTITY);
  expect(identity.productBuild).toMatch(/^\d+\.\d+\.\d+\.\d+$/);
  expect(identity.hostId).toBe("creator-web");
  expect(identity.hostVersion).toMatch(/^\d+\.\d+\.\d+$/);
  expect(identity.platformVersion).toMatch(/^\d+\.\d+\.\d+$/);
  expect(Number.isSafeInteger(identity.protocolVersion)).toBe(true);
});
