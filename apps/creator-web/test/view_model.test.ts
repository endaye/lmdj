import {expect, test} from "vitest";

import {padAddress, slotAddress} from "../src/state/view_model";

test("addresses a Pad as its Bank letter and a two-digit Pad number", () => {
  expect(slotAddress(0)).toBe("A01");
  expect(slotAddress(9)).toBe("A10");
  expect(slotAddress(15)).toBe("A16");
  expect(slotAddress(16)).toBe("B01");
  expect(slotAddress(63)).toBe("D16");
  expect(padAddress({slot: 34, assetId: null})).toBe("C03");
});
