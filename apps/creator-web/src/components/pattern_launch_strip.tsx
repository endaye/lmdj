import {useEffect, useState} from "react";

import type {Bank} from "../state/creator_state";
import type {PerformState} from "../state/perform_state";

interface PatternLaunchStripProps {
  readonly slots: readonly (string | null)[];
  readonly patterns: readonly Readonly<{patternId: string}>[];
  readonly pending: PerformState["pendingLaunch"];
  readonly lastAck: PerformState["lastLaunchAck"];
  readonly bank: Bank;
  readonly disabled?: boolean;
  readonly mutationDisabled?: boolean;
  readonly onBankChange: (bank: Bank) => void;
  readonly onLaunch: (patternSlot: number) => void;
  readonly onAssign: (patternSlot: number, patternId: string) => void;
  readonly onClear: (patternSlot: number) => void;
  readonly onMove: (fromSlot: number, toSlot: number) => void;
}

const BANKS = ["A", "B", "C", "D"] as const;

export function PatternLaunchStrip(props: PatternLaunchStripProps) {
  const [patternId, setPatternId] = useState(props.patterns[0]?.patternId ?? "");
  const [assignmentSlot, setAssignmentSlot] = useState(0);
  const [clearSlot, setClearSlot] = useState(0);
  const [moveFrom, setMoveFrom] = useState(0);
  const [moveTo, setMoveTo] = useState(1);
  useEffect(() => {
    if (!props.patterns.some((pattern) => pattern.patternId === patternId)) {
      setPatternId(props.patterns[0]?.patternId ?? "");
    }
  }, [patternId, props.patterns]);
  const slotOptions = props.slots.map((_value, index) => (
    <option value={index} key={index}>{index + 1}</option>
  ));
  return (
    <section className="perform-patterns" aria-label="Pattern Launch">
      <div className="perform-bank" role="group" aria-label="Perform Bank">
        {BANKS.map((label, bank) => (
          <button type="button" key={label} aria-label={`Bank ${label}`}
            aria-pressed={props.bank === bank}
            onClick={() => props.onBankChange(bank as Bank)}>{label}</button>
        ))}
      </div>
      <div className="perform-pattern-editor" role="group" aria-label="Pattern slot editing">
        <label>Pattern assignment
          <select aria-label="Pattern assignment" value={patternId}
            disabled={props.mutationDisabled || props.patterns.length === 0}
            onChange={(event) => setPatternId(event.currentTarget.value)}>
            {props.patterns.map((pattern) => (
              <option value={pattern.patternId} key={pattern.patternId}>
                {pattern.patternId.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        <label>Pattern slot
          <select aria-label="Pattern slot" value={assignmentSlot}
            disabled={props.mutationDisabled}
            onChange={(event) => setAssignmentSlot(Number(event.currentTarget.value))}>
            {slotOptions}
          </select>
        </label>
        <button type="button" disabled={props.mutationDisabled || patternId === ""}
          onClick={() => props.onAssign(assignmentSlot, patternId)}>Assign Pattern</button>
        <label>Clear Pattern slot
          <select aria-label="Clear Pattern slot" value={clearSlot}
            disabled={props.mutationDisabled}
            onChange={(event) => setClearSlot(Number(event.currentTarget.value))}>
            {slotOptions}
          </select>
        </label>
        <button type="button" disabled={props.mutationDisabled}
          onClick={() => props.onClear(clearSlot)}>Clear Pattern</button>
        <label>Move Pattern from
          <select aria-label="Move Pattern from" value={moveFrom}
            disabled={props.mutationDisabled}
            onChange={(event) => setMoveFrom(Number(event.currentTarget.value))}>
            {slotOptions}
          </select>
        </label>
        <label>Move Pattern to
          <select aria-label="Move Pattern to" value={moveTo}
            disabled={props.mutationDisabled}
            onChange={(event) => setMoveTo(Number(event.currentTarget.value))}>
            {slotOptions}
          </select>
        </label>
        <button type="button" disabled={props.mutationDisabled || moveFrom === moveTo}
          onClick={() => props.onMove(moveFrom, moveTo)}>Move Pattern</button>
      </div>
      <div className="perform-pattern-slots" role="group" aria-label="Pattern slots">
        {props.slots.map((patternId, patternSlot) => (
          <button type="button" key={patternSlot}
            aria-label={`Launch Pattern ${patternSlot + 1}`}
            aria-busy={props.pending?.patternSlot === patternSlot}
            data-pattern-id={patternId ?? undefined}
            data-launch={props.pending?.patternSlot === patternSlot ? "pending" :
              props.lastAck?.patternSlot === patternSlot ? "acknowledged" : "idle"}
            disabled={props.disabled}
            onClick={() => props.onLaunch(patternSlot)}>
            {patternSlot + 1} · {patternId === null ? "Empty" : patternId.slice(0, 8)}
          </button>
        ))}
      </div>
      <output role="status" aria-label="Pattern launch status">
        {props.pending !== null
          ? `Pattern ${props.pending.patternSlot + 1} pending`
          : props.lastAck !== null
            ? `Pattern ${props.lastAck.patternSlot + 1} acknowledged${
              props.slots[props.lastAck.patternSlot] === null ? " · silent gap" : ""}`
            : "idle"}
      </output>
    </section>
  );
}
