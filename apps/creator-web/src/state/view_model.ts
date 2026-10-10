import type {Bank, ProjectPadView} from "./creator_state";

export const BANK_NAMES = ["A", "B", "C", "D"] as const;

// Display traversal only: local Pad identity and input mappings stay stable.
// DOM order follows the rows so keyboard focus follows the visible matrix.
export const PAD_MATRIX_ORDER = Object.freeze([
  12, 13, 14, 15,
  8, 9, 10, 11,
  4, 5, 6, 7,
  0, 1, 2, 3,
] as const);

export function bankName(bank: Bank): (typeof BANK_NAMES)[Bank] {
  return BANK_NAMES[bank];
}

// A Pad address is the Bank letter plus a two-digit Pad number: A01–D16.
export function slotAddress(slot: number): string {
  const bank = Math.floor(slot / 16) as Bank;
  return `${bankName(bank)}${String((slot % 16) + 1).padStart(2, "0")}`;
}

export function padAddress(pad: Pick<ProjectPadView, "slot" | "assetId">): string {
  return slotAddress(pad.slot);
}

export function shortProjectId(projectId: string): string {
  return projectId.slice(0, 8);
}
