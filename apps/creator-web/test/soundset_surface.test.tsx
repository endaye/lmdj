import {render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";

import {SoundSetSurface} from "../src/components/soundset_surface";
import type {
  CreatorSoundSetRuntimeSession,
  SoundSetCatalog,
  SoundSetInspect,
  SoundSetMapPreview,
  SoundSetSlot,
  SoundSetSummary,
} from "../src/runtime/runtime_types";

const FOUNDRY = {
  setId: "11111111-1111-4111-8111-111111111111",
  version: "1.0.0",
  manifestSha256: "33175f66912a9add3e4e551d19d85072adcd1f0331fcc9fed80ab0bc18dd9111",
};
const ATTRIBUTION_KIT = {
  setId: "22222222-2222-4222-8222-222222222222",
  version: "1.0.0",
  manifestSha256: "ae578e4f6a383994fb15fd984d7906e346ee7bcb6d7add763c8da9317a313bb4",
};
// The fixture corpus' own string: `tests/fixtures/soundset` builds the
// `CC-BY-4.0` Set with exactly this attribution.
const ATTRIBUTION = "Fixture Attribution Kit by Bea Waveform (CC BY 4.0)";

function artifact(seed: string) {
  return {sha256: seed.repeat(32), mediaType: "audio/wav", byteLength: 2_048};
}

function occupiedSlot(slot: number, role: string, name: string): SoundSetSlot {
  return {
    slot,
    role,
    name,
    bpm: null,
    key: null,
    artifact: artifact(String(slot % 10) + "a"),
    audio: {
      sampleRate: 44_100,
      channels: 1,
      sourceFrames: 1_024,
      preparedBytes: 4_096,
      preparedFrames: 1_024,
    },
  };
}

// S11-D12: an empty Set slot carries no Artifact at all.
function emptySlot(slot: number): SoundSetSlot {
  return {slot, artifact: null};
}

function summary(
  identity: typeof FOUNDRY,
  overrides: Partial<SoundSetSummary> = {},
): SoundSetSummary {
  return {
    ...identity,
    name: "Fixture Foundry CC0",
    publisher: "LMDJ Fixtures",
    description: null,
    bpm: 120,
    key: "Am",
    totalBytes: 127_096,
    hasDemo: true,
    license: {
      spdxId: "CC0-1.0",
      rightsHolder: "LMDJ Fixtures",
      copyright: "(c) 2026 LMDJ Fixtures",
      attribution: "",
    },
    occupiedSlots: [{slot: 0, role: "kick", name: "Kick"}],
    ...overrides,
  };
}

const ATTRIBUTION_SUMMARY = summary(ATTRIBUTION_KIT, {
  name: "Fixture Attribution Kit",
  publisher: "Bea Waveform",
  totalBytes: 34_788,
  license: {
    spdxId: "CC-BY-4.0",
    rightsHolder: "Bea Waveform",
    copyright: "(c) 2026 Bea Waveform",
    attribution: ATTRIBUTION,
  },
  occupiedSlots: [0, 1, 2, 3].map((slot) => ({
    slot,
    role: "kick",
    name: `Sound ${slot}`,
  })),
});

function inspect(
  base: SoundSetSummary,
  occupied: readonly number[],
): SoundSetInspect {
  return {
    ...base,
    demo: base.hasDemo ? artifact("f0") : null,
    slots: Array.from({length: 16}, (_, slot) =>
      occupied.includes(slot)
        ? occupiedSlot(slot, "kick", `Sound ${slot}`)
        : emptySlot(slot)),
  };
}

function mapPreview(
  base: SoundSetSummary,
  occupied: readonly number[],
  collisions: readonly number[],
  bankId = 0,
): SoundSetMapPreview {
  return {
    setId: base.setId,
    version: base.version,
    manifestSha256: base.manifestSha256,
    bankId,
    // Deliberately not the `projectRevision` prop the surface is rendered
    // with: the install must carry the revision its mapping was computed
    // against, and identical numbers could not tell the two apart.
    projectRevision: 4,
    proposed: occupied.map((pad) => ({
      slotIndex: pad,
      pad,
      artifact: artifact(String(pad % 10) + "a"),
    })),
    collisions: [...collisions],
    kept: Array.from({length: 16}, (_, pad) => pad)
      .filter((pad) => !occupied.includes(pad)),
  };
}

function fakeSession(overrides: Partial<CreatorSoundSetRuntimeSession> = {}) {
  const catalog: SoundSetCatalog = {
    catalogAvailable: true,
    sets: [summary(FOUNDRY), ATTRIBUTION_SUMMARY],
    refused: [],
  };
  return {
    listSoundSets: vi.fn(async () => catalog),
    inspectSoundSet: vi.fn(async (request: {manifestSha256: string}) =>
      request.manifestSha256 === ATTRIBUTION_KIT.manifestSha256
        ? inspect(ATTRIBUTION_SUMMARY, [0, 1, 2, 3])
        : inspect(summary(FOUNDRY), [0])),
    previewSoundSetMap: vi.fn(async () =>
      mapPreview(summary(FOUNDRY), [0], [])),
    installSoundSet: vi.fn(async () => ({
      ...FOUNDRY,
      bankId: 0,
      committedRevision: 5,
      replayed: false,
      installed: [{slotIndex: 0, pad: 0}],
      collisions: [],
      kept: [],
    })),
    auditionSoundSet: vi.fn(async (request: {slotIndex?: number}) => ({
      ...FOUNDRY,
      slotIndex: request.slotIndex ?? null,
      artifact: artifact("0a"),
      // #799. The Host reports whether a voice actually started; a fake that
      // omitted it would model a reply the session cannot produce.
      played: true,
      audio: {
        sampleRate: 48_000,
        channels: 1,
        sourceFrames: 1_024,
        preparedBytes: 4_456,
        preparedFrames: 1_114,
      },
    })),
    stopSoundSetAudition: vi.fn(async () => ({accepted: true as const})),
    ...overrides,
  } as unknown as CreatorSoundSetRuntimeSession & {
    listSoundSets: ReturnType<typeof vi.fn>;
    inspectSoundSet: ReturnType<typeof vi.fn>;
    previewSoundSetMap: ReturnType<typeof vi.fn>;
    installSoundSet: ReturnType<typeof vi.fn>;
    auditionSoundSet: ReturnType<typeof vi.fn>;
    stopSoundSetAudition: ReturnType<typeof vi.fn>;
  };
}

function renderSurface(
  session: CreatorSoundSetRuntimeSession,
  props: {projectRevision?: number | null} = {},
) {
  return render(
    <SoundSetSurface
      session={session}
      projectRevision={props.projectRevision === undefined
        ? 9
        : props.projectRevision}
      activeBank={0}
    />,
  );
}

test("the CC-BY-4.0 attribution string is shown on listing and on inspect", async () => {
  const session = fakeSession();
  renderSurface(session);

  const listed = await screen.findByRole("button", {
    name: "Inspect Fixture Attribution Kit",
  });
  // On listing: the attribution travels with the Set in the catalog list.
  const card = listed.closest("li");
  expect(card).not.toBeNull();
  expect(within(card as HTMLElement).getByText(ATTRIBUTION)).toBeTruthy();
  // A CC0 Set declares an empty attribution and shows no attribution row.
  const cc0 = (await screen.findByRole("button", {
    name: "Inspect Fixture Foundry CC0",
  })).closest("li") as HTMLElement;
  expect(within(cc0).queryByText("Attribution")).toBeNull();

  await userEvent.click(listed);

  // On inspect: the same string, from the verified manifest.
  const panel = await screen.findByRole("region", {
    name: "Sound Set Fixture Attribution Kit",
  });
  expect(within(panel).getByText(`Attribution: ${ATTRIBUTION}`)).toBeTruthy();
});

test("listing a cached Set with the Catalog unreachable still offers inspect and install", async () => {
  const session = fakeSession({
    listSoundSets: vi.fn(async () => ({
      catalogAvailable: false,
      sets: [summary(FOUNDRY)],
      refused: [],
    })),
  } as Partial<CreatorSoundSetRuntimeSession>);
  renderSurface(session);

  expect((await screen.findByRole("status")).textContent).toContain(
    "Catalog unreachable",
  );

  // Inspect is offered, and it answers from the Workspace Set Store.
  await userEvent.click(
    await screen.findByRole("button", {name: "Inspect Fixture Foundry CC0"}),
  );
  const panel = await screen.findByRole("region", {
    name: "Sound Set Fixture Foundry CC0",
  });

  // And so is install: the mapping previews and the confirmation is live.
  await userEvent.click(
    within(panel).getByRole("button", {name: /Preview mapping into Bank A/}),
  );
  const install = await within(panel).findByRole("button", {
    name: /^Install 1 of 16 into Bank A$/,
  });
  expect((install as HTMLButtonElement).disabled).toBe(false);
  await userEvent.click(install);
  await waitFor(() => {
    expect(session.installSoundSet).toHaveBeenCalledTimes(1);
  });
});

test("a collision cannot be submitted without keep or replace", async () => {
  const session = fakeSession({
    previewSoundSetMap: vi.fn(async () =>
      mapPreview(summary(FOUNDRY), [0, 1, 2], [1, 2])),
  } as Partial<CreatorSoundSetRuntimeSession>);
  renderSurface(session);

  await userEvent.click(
    await screen.findByRole("button", {name: "Inspect Fixture Foundry CC0"}),
  );
  await userEvent.click(
    await screen.findByRole("button", {name: /Preview mapping into Bank A/}),
  );

  const keep = await screen.findByRole("radio", {
    name: "Keep the Pads I already have",
  });
  const replace = screen.getByRole("radio", {
    name: "Replace them with this Set",
  });
  // Neither is pre-selected: the Host never substitutes a default policy.
  expect((keep as HTMLInputElement).checked).toBe(false);
  expect((replace as HTMLInputElement).checked).toBe(false);
  const undecided = screen.getByRole("button", {name: "Install into Bank A"});
  expect((undecided as HTMLButtonElement).disabled).toBe(true);
  expect(session.installSoundSet).not.toHaveBeenCalled();

  await userEvent.click(keep);
  // `keep` writes only the one Pad that was free.
  const install = screen.getByRole("button", {
    name: "Install 1 of 16 into Bank A",
  });
  expect((install as HTMLButtonElement).disabled).toBe(false);
  await userEvent.click(install);

  await waitFor(() => {
    expect(session.installSoundSet).toHaveBeenCalledTimes(1);
  });
  expect(session.installSoundSet.mock.calls[0]?.[0]).toMatchObject({
    occupiedPadPolicy: "keep",
    bankId: 0,
    // The mapping's revision (4), not the live prop (9).
    expectedRevision: 4,
  });
});

test("a mapping with no collision carries no occupied Pad policy at all", async () => {
  const session = fakeSession();
  renderSurface(session);

  await userEvent.click(
    await screen.findByRole("button", {name: "Inspect Fixture Foundry CC0"}),
  );
  await userEvent.click(
    await screen.findByRole("button", {name: /Preview mapping into Bank A/}),
  );
  expect(screen.queryByRole("radio")).toBeNull();
  await userEvent.click(
    await screen.findByRole("button", {name: "Install 1 of 16 into Bank A"}),
  );

  await waitFor(() => {
    expect(session.installSoundSet).toHaveBeenCalledTimes(1);
  });
  const request = session.installSoundSet.mock.calls[0]?.[0] as
    Record<string, unknown>;
  expect(Object.hasOwn(request, "occupiedPadPolicy")).toBe(false);
});

test("an empty Set slot is never presented as a clear-Pad action", async () => {
  const session = fakeSession();
  renderSurface(session);

  await userEvent.click(
    await screen.findByRole("button", {name: "Inspect Fixture Foundry CC0"}),
  );
  const slots = await screen.findByRole("list", {name: "Sound Set slots"});
  const empty = within(slots).getAllByText("Empty in this Set");
  expect(empty).toHaveLength(15);
  // Not a button, not a checkbox, not a link: nothing to press.
  for (const label of empty) {
    const row = label.closest("li") as HTMLElement;
    expect(row.dataset.empty).toBe("true");
    expect(within(row).queryByRole("button")).toBeNull();
    expect(within(row).queryByRole("checkbox")).toBeNull();
    expect(within(row).queryByRole("link")).toBeNull();
  }
  expect(within(slots).queryByText(/clear/i)).toBeNull();

  await userEvent.click(
    await screen.findByRole("button", {name: /Preview mapping into Bank A/}),
  );
  const matrix = await screen.findByLabelText("Proposed Bank mapping");
  const untouched = within(matrix)
    .getAllByText("Empty in Set — Pad unchanged");
  expect(untouched).toHaveLength(15);
  expect(within(matrix).queryByRole("button")).toBeNull();
});

test("a refused Set names its public reason instead of vanishing", async () => {
  const session = fakeSession({
    listSoundSets: vi.fn(async () => ({
      catalogAvailable: true,
      sets: [],
      refused: [{
        setId: "66666666-6666-4666-8666-666666666666",
        version: "1.0.0",
        manifestSha256: "9b".repeat(32),
        code: "PERMISSION_DENIED",
        reason: "soundset_license_ineligible",
      }],
    })),
  } as Partial<CreatorSoundSetRuntimeSession>);
  renderSurface(session);

  const refused = await screen.findByRole("list", {
    name: "Unavailable Sound Sets",
  });
  expect(refused.textContent).toContain("PERMISSION_DENIED");
  expect(refused.textContent).toContain("soundset_license_ineligible");
});

test("an install refusal is reported with the locked reason and no Project change", async () => {
  const session = fakeSession({
    installSoundSet: vi.fn(async () => {
      throw Object.assign(new Error("Sound Set audio is not supported"), {
        code: "UNSUPPORTED_AUDIO",
        details: {reason: "soundset_audio_unsupported"},
      });
    }),
  } as Partial<CreatorSoundSetRuntimeSession>);
  renderSurface(session);

  await userEvent.click(
    await screen.findByRole("button", {name: "Inspect Fixture Foundry CC0"}),
  );
  await userEvent.click(
    await screen.findByRole("button", {name: /Preview mapping into Bank A/}),
  );
  await userEvent.click(
    await screen.findByRole("button", {name: "Install 1 of 16 into Bank A"}),
  );

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain(
    "Accepted Set audio: PCM16 WAV, mono or stereo, 44.1 or 48 kHz",
  );
});

test("a Set cannot be installed before a Project is open", async () => {
  const session = fakeSession();
  renderSurface(session, {projectRevision: null});

  await userEvent.click(
    await screen.findByRole("button", {name: "Inspect Fixture Foundry CC0"}),
  );
  expect(((await screen.findByRole("button", {
    name: /Preview mapping into Bank A/,
  })) as HTMLButtonElement).disabled).toBe(true);
  expect(session.previewSoundSetMap).not.toHaveBeenCalled();
});

// #799 Task 4b. The two attachment points the surface documented for three
// Stages: the set-level demo and one occupied slot. Each dispatches exactly one
// audition, addressed the way S11-D5 defines -- no `slotIndex` for the demo,
// the slot's own index for a slot.
test("the set demo control auditions the Set without a slot index", async () => {
  const session = fakeSession();
  renderSurface(session);
  await userEvent.click(
    await screen.findByRole("button", {name: "Inspect Fixture Attribution Kit"}));
  await userEvent.click(
    await screen.findByRole("button", {name: "Audition set demo"}));
  await waitFor(() => expect(session.auditionSoundSet).toHaveBeenCalledTimes(1));
  const request = session.auditionSoundSet.mock.calls[0]![0]!;
  // The demo is addressed by Set identity alone. A `slotIndex` here would
  // audition slot 0's Artifact instead, which for the Attribution Kit is the
  // same bytes -- so asserting its absence is the only way to tell them apart.
  expect(request.slotIndex).toBeUndefined();
  expect(request.manifestSha256).toBe(ATTRIBUTION_KIT.manifestSha256);
});

test("an occupied slot control auditions that slot", async () => {
  const session = fakeSession();
  renderSurface(session);
  await userEvent.click(
    await screen.findByRole("button", {name: "Inspect Fixture Attribution Kit"}));
  const slots = await screen.findByRole("list", {name: "Sound Set slots"});
  const controls = within(slots).getAllByRole("button", {name: /^Audition /});
  // Only occupied slots carry a control: `slotIsEmpty` decides, and an empty
  // Set slot is not an action the user can take.
  expect(controls).toHaveLength(4);
  await userEvent.click(controls[2]!);
  await waitFor(() => expect(session.auditionSoundSet).toHaveBeenCalledTimes(1));
  expect(session.auditionSoundSet.mock.calls[0]![0]!.slotIndex).toBe(2);
});

test("the stop control stops without addressing a Set", async () => {
  const session = fakeSession();
  renderSurface(session);
  await userEvent.click(
    await screen.findByRole("button", {name: "Inspect Fixture Attribution Kit"}));
  await userEvent.click(
    await screen.findByRole("button", {name: "Stop audition"}));
  await waitFor(() =>
    expect(session.stopSoundSetAudition).toHaveBeenCalledTimes(1));
  // Stopping names no Set: there is only ever one audition, so a Set argument
  // would be a field this surface could get wrong.
  expect(session.stopSoundSetAudition.mock.calls[0]!).toHaveLength(0);
});

test("an audition refusal reaches the surface instead of being swallowed", async () => {
  const session = fakeSession({
    auditionSoundSet: vi.fn(async () => {
      throw {code: "UNSUPPORTED_AUDIO", message: "Sound Set audio is unsupported",
             details: {reason: "soundset_audio_unsupported"}};
    }),
  });
  renderSurface(session);
  await userEvent.click(
    await screen.findByRole("button", {name: "Inspect Fixture Attribution Kit"}));
  await userEvent.click(
    await screen.findByRole("button", {name: "Audition set demo"}));
  // A refusal the Facade already decided must be shown, not dropped: this
  // surface plays nothing itself, so a swallowed error is indistinguishable
  // from an audition that simply made no sound.
  //
  // The assertion is on the guidance, not on the raw `soundset_audio_unsupported`
  // token, because the surface maps locked reasons to guidance rather than
  // printing them -- and the guidance is what proves the *typed* reason was
  // understood. Any thrown object would produce a message; only this one
  // produces the S8-D6 accepted-audio line.
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Sound Set audio is unsupported");
  expect(alert.textContent).toContain(
    "Accepted Set audio: PCM16 WAV, mono or stereo, 44.1 or 48 kHz");
});

test("install target is explicit and independent of the playing Bank", async () => {
  const session = fakeSession();
  const view = renderSurface(session);
  await userEvent.click(await screen.findByRole("button", {name: "Inspect Fixture Foundry CC0"}));
  expect(await screen.findByText("Choose where to install. This does not change the playing Bank.")).toBeTruthy();
  const targets = screen.getByRole("group", {name: "Install target Bank"});
  await userEvent.click(within(targets).getByRole("button", {name: "Install target Bank C"}));
  view.rerender(<SoundSetSurface session={session} projectRevision={9} activeBank={1} />);
  expect(within(targets).getByRole("button", {name: "Install target Bank C"})
    .getAttribute("aria-pressed")).toBe("true");
  await userEvent.click(screen.getByRole("button", {name: "Preview mapping into Bank C"}));
  await waitFor(() => expect(session.previewSoundSetMap).toHaveBeenCalledWith(
    expect.objectContaining({bankId: 2}),
  ));
});
