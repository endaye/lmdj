import type {Bank} from "../state/creator_state";
import {BANK_NAMES} from "../state/view_model";

interface BankSelectorProps {
  activeBank: Bank;
  onSelect: (bank: Bank) => void;
}

export function BankSelector({activeBank, onSelect}: BankSelectorProps) {
  return (
    <div className="bank-selector" aria-label="Pad Banks">
      {BANK_NAMES.map((name, bank) => (
        <button
          type="button"
          className={bank === activeBank ? "is-active" : undefined}
          aria-pressed={bank === activeBank}
          aria-label={`Bank ${name}`}
          key={name}
          onClick={() => onSelect(bank as Bank)}
        >
          {name}
        </button>
      ))}
    </div>
  );
}
