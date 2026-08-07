import type {Bank, ProjectPadView} from "./creator_state";

export const BANK_NAMES = ["A", "B", "C", "D"] as const;

export function bankName(bank: Bank): (typeof BANK_NAMES)[Bank] {
  return BANK_NAMES[bank];
}

export function padAddress(pad: ProjectPadView): string {
  const bank = Math.floor(pad.slot / 16) as Bank;
  return `${bankName(bank)}${(pad.slot % 16) + 1}`;
}

export function shortProjectId(projectId: string): string {
  return projectId.slice(0, 8);
}
