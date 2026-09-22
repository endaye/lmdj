import type {Bank} from "../state/creator_state";
import {BANK_NAMES} from "../state/view_model";

interface BankSelectorProps {
  activeBank: Bank;
  purpose?: "install";
  onSelect: (bank: Bank) => void;
}

export function BankSelector({activeBank, onSelect, purpose}: BankSelectorProps) {
  const label = purpose === "install" ? "Install target Bank" : "Bank";
  return (
    <div className="bank-selector" role="group" aria-label={purpose === "install" ? "Install target Bank" : "Pad Banks"}>
      {BANK_NAMES.map((name, bank) => (
        <button
          type="button"
          className={bank === activeBank ? "is-active" : undefined}
          aria-pressed={bank === activeBank}
          aria-label={`${label} ${name}`}
          key={name}
          onClick={() => onSelect(bank as Bank)}
        >
          {purpose === "install" ? `Bank ${name}` : name}
        </button>
      ))}
    </div>
  );
}
