import type {Bank, ProjectPadView} from "./creator_state";

export const BANK_NAMES = ["A", "B", "C", "D"] as const;

export function bankName(bank: Bank): (typeof BANK_NAMES)[Bank] {
  return BANK_NAMES[bank];
}

// A Pad address is the Bank letter plus a two-digit Pad number: A01–D16.
export function slotAddress(slot: number): string {
  const bank = Math.floor(slot / 16) as Bank;
  return `${bankName(bank)}${String((slot % 16) + 1).padStart(2, "0")}`;
}

export function padAddress(pad: ProjectPadView): string {
  return slotAddress(pad.slot);
}

export function shortProjectId(projectId: string): string {
  return projectId.slice(0, 8);
}
