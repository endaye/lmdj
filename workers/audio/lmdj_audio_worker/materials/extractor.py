from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import numpy as np

from lmdj_core_models.materials import (
    MATERIAL_SLOT_BY_INDEX,
    Material,
    MaterialEvent,
    MaterialPackage,
    MaterialPattern,
    MaterialPlayback,
    MaterialProvenance,
    MaterialQuality,
    MaterialSource,
    MaterialTiming,
    SlotDecision,
)

from lmdj_audio_worker.materials.audio import (
    clipping_ratio,
    crossfade_loop,
    mono,
    normalize_and_fade,
    normalized_feature_difference,
    read_audio,
    rms,
    spectral_features,
    write_wav,
)
from lmdj_audio_worker.materials.config import (
    DEFAULT_MATERIAL_CONFIG,
    MaterialExtractionConfig,
)
from lmdj_audio_worker.materials.package_writer import write_material_package
from lmdj_audio_worker.materials.timing import TimingArtifact, TimeWindow


@dataclass(frozen=True)
class Candidate:
    role: str
    start: float
    end: float
    audio: np.ndarray
    quality: float
    features: tuple[float, ...]


class MaterialExtractor:
    def __init__(
        self,
        config: MaterialExtractionConfig = DEFAULT_MATERIAL_CONFIG,
    ) -> None:
        self.config = config

    def extract(
        self,
        *,
        original_audio: Path,
        stems_dir: Path,
        timing: TimingArtifact,
        output_dir: Path,
        provenance: MaterialProvenance,
    ) -> MaterialPackage:
        output_dir.mkdir(parents=True, exist_ok=True)
        sample_dir = output_dir / "samples"
        source_audio = read_audio(original_audio, self.config.sample_rate)
        stem_audio: dict[str, np.ndarray | None] = {}
        for name in ("drums", "bass", "vocals", "other"):
            path = stems_dir / f"{name}.wav"
            stem_audio[name] = (
                read_audio(path, self.config.sample_rate)
                if path.is_file()
                else None
            )

        selected: dict[int, Candidate] = {}
        reasons: dict[int, str] = {}
        drum_onsets: list[tuple[float, str, tuple[float, ...]]] = []
        drums = stem_audio["drums"]
        if drums is None:
            for index in range(4):
                reasons[index] = "source_stem_unavailable"
                reasons[index + 8] = "source_stem_unavailable"
        elif rms(drums) < self.config.silence_rms:
            for index in range(4):
                reasons[index] = "source_silent"
                reasons[index + 8] = "source_silent"
        elif (
            clipping_ratio(drums) > self.config.clipping_ratio_limit
            or _stem_leakage_ratio(
                drums,
                [
                    stem
                    for name, stem in stem_audio.items()
                    if name != "drums" and stem is not None
                ],
            )
            > self.config.leakage_ratio_limit
        ):
            for index in range(4):
                reasons[index] = "quality_below_threshold"
                reasons[index + 8] = "quality_below_threshold"
        else:
            by_role, drum_onsets = self._drum_candidates(drums, timing)
            for index, role in enumerate(("kick", "snare", "hat", "percussion")):
                self._select_variants(
                    by_role.get(role, []),
                    index,
                    selected,
                    reasons,
                    empty_reason="no_candidate",
                )

        for index, (role, stem_name) in enumerate(
            (("bass", "bass"), ("melody", "other"), ("vocal", "vocals")),
            start=4,
        ):
            stem = stem_audio[stem_name]
            if stem is None:
                reasons[index] = "source_stem_unavailable"
                reasons[index + 8] = "source_stem_unavailable"
            elif rms(stem) < self.config.silence_rms:
                reasons[index] = "source_silent"
                reasons[index + 8] = "source_silent"
            elif (
                clipping_ratio(stem) > self.config.clipping_ratio_limit
                or _stem_leakage_ratio(
                    stem,
                    [
                        other
                        for other_name, other in stem_audio.items()
                        if other_name != stem_name and other is not None
                    ],
                )
                > self.config.leakage_ratio_limit
            ):
                reasons[index] = "quality_below_threshold"
                reasons[index + 8] = "quality_below_threshold"
            else:
                self._select_variants(
                    self._loop_candidates(role, stem, timing),
                    index,
                    selected,
                    reasons,
                    empty_reason="no_valid_loop_boundary",
                )

        if clipping_ratio(source_audio) > self.config.clipping_ratio_limit:
            reasons[7] = "quality_below_threshold"
            reasons[15] = "quality_below_threshold"
        else:
            self._select_variants(
                self._loop_candidates("full_mix_phrase", source_audio, timing),
                7,
                selected,
                reasons,
                empty_reason="no_valid_loop_boundary",
            )
        if not selected:
            raise ValueError("material extraction produced zero accepted materials")

        materials: list[Material] = []
        material_features: dict[str, tuple[float, ...]] = {}
        for slot_index in sorted(selected):
            candidate = selected[slot_index]
            slot = MATERIAL_SLOT_BY_INDEX[slot_index]
            variant = slot.variant.lower()
            role_file = (
                "phrase"
                if slot.role == "full_mix_phrase"
                else slot.role.replace("_", "-")
            )
            path = f"samples/{role_file}-{variant}.wav"
            processed = (
                normalize_and_fade(
                    candidate.audio,
                    self.config.sample_rate,
                    self.config.one_shot_fade_seconds,
                )
                if slot.kind == "one_shot"
                else crossfade_loop(
                    normalize_and_fade(
                        candidate.audio,
                        self.config.sample_rate,
                        self.config.one_shot_fade_seconds,
                    ),
                    self.config.sample_rate,
                    self.config.loop_crossfade_seconds,
                )
            )
            write_wav(output_dir / path, processed, self.config.sample_rate)
            material_id = f"mat_{role_file.replace('-', '_')}_{variant}"
            parent_id = (
                f"mat_{role_file.replace('-', '_')}_a"
                if slot.variant == "B"
                else None
            )
            material = Material(
                material_id=material_id,
                slot_index=slot_index,
                role=slot.role,
                variant=slot.variant,
                variant_of=parent_id,
                kind=slot.kind,
                source_stem=slot.source_stem,
                audio_path=path,
                playback=MaterialPlayback(
                    exclusive_group=(
                        "full_mix_exclusive"
                        if slot.kind == "full_mix_phrase"
                        else None
                    )
                ),
                quality=MaterialQuality(
                    status="accepted",
                    score=round(candidate.quality, 6),
                ),
            )
            materials.append(material)
            material_features[material_id] = candidate.features

        decisions = tuple(
            SlotDecision(
                slot_index=index,
                status="accepted" if index in selected else "empty",
                material_id=(
                    next(
                        material.material_id
                        for material in materials
                        if material.slot_index == index
                    )
                    if index in selected
                    else None
                ),
                reason=None if index in selected else reasons.get(index, "no_candidate"),
            )
            for index in range(16)
        )
        events = self._pattern_events(
            materials,
            material_features,
            drum_onsets,
            timing,
        )
        package = MaterialPackage(
            source=MaterialSource(audio_sha256=_sha256_file(original_audio)),
            provenance=provenance,
            timing=MaterialTiming(
                bpm=timing.bpm,
                beats_per_bar=timing.beats_per_bar,
                grid_per_beat=timing.grid_per_beat,
                length_steps=timing.length_steps,
                artifact="timing.json",
            ),
            materials=tuple(materials),
            pattern=MaterialPattern(
                pattern_id="pattern_primary",
                length_steps=timing.length_steps,
                events=tuple(events),
            ),
            slot_decisions=decisions,
        )
        write_material_package(output_dir, package)
        return package

    def _drum_candidates(
        self,
        audio: np.ndarray,
        timing: TimingArtifact,
    ) -> tuple[dict[str, list[Candidate]], list[tuple[float, str, tuple[float, ...]]]]:
        signal = mono(audio)
        frame = max(1, int(self.config.onset_frame_seconds * self.config.sample_rate))
        count = len(signal) // frame
        if count < 3:
            return {}, []
        framed = signal[: count * frame].reshape(count, frame)
        energy = np.sqrt(np.mean(np.square(framed, dtype=np.float64), axis=1))
        novelty = np.maximum(0.0, np.diff(energy, prepend=energy[0]))
        median = float(np.median(novelty))
        mad = float(np.median(np.abs(novelty - median))) + 1e-9
        threshold = max(
            median + self.config.onset_threshold_mad * mad,
            self.config.silence_rms * 2,
        )
        peak_frames = [
            index
            for index in range(1, len(novelty) - 1)
            if novelty[index] >= threshold
            and novelty[index] >= novelty[index - 1]
            and novelty[index] > novelty[index + 1]
        ]
        primary = timing.primary_window
        by_role: dict[str, list[Candidate]] = {
            "kick": [],
            "snare": [],
            "hat": [],
            "percussion": [],
        }
        records = []
        for position, frame_index in enumerate(peak_frames):
            start = frame_index * frame / self.config.sample_rate
            if not primary.start <= start < primary.end:
                continue
            next_time = (
                peak_frames[position + 1] * frame / self.config.sample_rate
                if position + 1 < len(peak_frames)
                else start + self.config.one_shot_max_seconds
            )
            duration = min(
                self.config.one_shot_max_seconds,
                max(self.config.one_shot_min_seconds, next_time - start),
            )
            start_frame = max(0, int(start * self.config.sample_rate))
            end_frame = min(
                len(audio),
                start_frame + int(duration * self.config.sample_rate),
            )
            sample = audio[start_frame:end_frame]
            if len(sample) < int(
                self.config.one_shot_min_seconds * self.config.sample_rate
            ):
                continue
            features = spectral_features(sample, self.config.sample_rate)
            role, confidence = _classify_drum(features)
            quality = self._quality(sample, confidence)
            candidate = Candidate(
                role=role,
                start=start,
                end=end_frame / self.config.sample_rate,
                audio=sample,
                quality=quality,
                features=features,
            )
            if quality >= self.config.quality_threshold:
                by_role[role].append(candidate)
                records.append((start, role, features))
        for candidates in by_role.values():
            candidates.sort(key=lambda item: (-item.quality, item.start))
        return by_role, records

    def _loop_candidates(
        self,
        role: str,
        audio: np.ndarray,
        timing: TimingArtifact,
    ) -> list[Candidate]:
        beat_seconds = 60.0 / timing.bpm
        starts = [timing.primary_window.start]
        starts.extend(window.start for window in timing.alternate_windows)
        starts.extend(timing.bars)
        candidates: list[Candidate] = []
        seen: set[tuple[int, int]] = set()
        for start in sorted(set(starts)):
            for bars in self.config.loop_bars:
                duration = bars * timing.beats_per_bar * beat_seconds
                end = start + duration
                begin_frame = int(round(start * self.config.sample_rate))
                end_frame = int(round(end * self.config.sample_rate))
                key = (begin_frame, end_frame)
                if key in seen or begin_frame < 0 or end_frame > len(audio):
                    continue
                seen.add(key)
                sample = audio[begin_frame:end_frame]
                features = spectral_features(sample, self.config.sample_rate)
                quality = self._quality(sample, _boundary_score(sample))
                if quality < self.config.quality_threshold:
                    continue
                candidates.append(
                    Candidate(
                        role=role,
                        start=start,
                        end=end,
                        audio=sample,
                        quality=quality,
                        features=features,
                    )
                )
        candidates.sort(key=lambda item: (-item.quality, item.start, item.end))
        return candidates

    def _quality(self, audio: np.ndarray, role_score: float) -> float:
        signal_rms = rms(audio)
        if signal_rms < self.config.silence_rms:
            return 0.0
        if clipping_ratio(audio) > self.config.clipping_ratio_limit:
            return 0.0
        energy_score = min(1.0, signal_rms / 0.05)
        cleanliness = 1.0 - min(
            1.0,
            clipping_ratio(audio) / self.config.clipping_ratio_limit,
        )
        return float(
            max(
                0.0,
                min(
                    1.0,
                    0.55 + 0.20 * role_score + 0.15 * energy_score
                    + 0.10 * cleanliness,
                ),
            )
        )

    def _select_variants(
        self,
        candidates: list[Candidate],
        a_index: int,
        selected: dict[int, Candidate],
        reasons: dict[int, str],
        *,
        empty_reason: str,
    ) -> None:
        if not candidates:
            reasons[a_index] = empty_reason
            reasons[a_index + 8] = empty_reason
            return
        first = candidates[0]
        selected[a_index] = first
        distinct = [
            candidate
            for candidate in candidates[1:]
            if normalized_feature_difference(
                first.features,
                candidate.features,
            )
            >= self.config.variant_difference_threshold
        ]
        if distinct:
            selected[a_index + 8] = distinct[0]
        else:
            reasons[a_index + 8] = "variant_not_distinct"

    def _pattern_events(
        self,
        materials: list[Material],
        material_features: dict[str, tuple[float, ...]],
        drum_onsets: list[tuple[float, str, tuple[float, ...]]],
        timing: TimingArtifact,
    ) -> list[MaterialEvent]:
        by_role: dict[str, list[Material]] = {}
        for material in materials:
            by_role.setdefault(material.role, []).append(material)
        events: set[tuple[str, int, int]] = set()
        step_seconds = 60.0 / timing.bpm / timing.grid_per_beat
        for onset, role, features in drum_onsets:
            options = by_role.get(role, [])
            if not options:
                continue
            material = min(
                options,
                key=lambda item: (
                    normalized_feature_difference(
                        features,
                        material_features[item.material_id],
                    ),
                    item.slot_index,
                ),
            )
            step = round(
                (onset - timing.primary_window.start) / step_seconds
            )
            if 0 <= step < timing.length_steps:
                events.add((material.material_id, step, 108))
        for role in ("bass", "melody", "vocal"):
            a = next(
                (
                    material
                    for material in by_role.get(role, [])
                    if material.variant == "A"
                ),
                None,
            )
            if a is not None:
                events.add((a.material_id, 0, 100))
        return [
            MaterialEvent(material_id, step, velocity)
            for material_id, step, velocity in sorted(
                events,
                key=lambda item: (item[1], item[0], item[2]),
            )
        ]


def _classify_drum(features: tuple[float, ...]) -> tuple[str, float]:
    low, mid, high, centroid, transient = features
    scores = {
        "kick": 0.65 * low + 0.20 * (1 - centroid) + 0.15 * transient,
        "snare": 0.55 * mid + 0.20 * high + 0.25 * transient,
        "hat": 0.65 * high + 0.25 * centroid + 0.10 * transient,
        "percussion": 0.35 * mid + 0.25 * high + 0.40 * transient,
    }
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    role, score = ordered[0]
    return role, float(min(1.0, score + 0.35))


def _boundary_score(audio: np.ndarray) -> float:
    edge = max(1, min(len(audio) // 20, 2048))
    scale = rms(audio) + 1e-9
    difference = rms(audio[:edge] - audio[-edge:]) / scale
    return float(max(0.0, min(1.0, 1.0 - difference / 2.0)))


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _stem_leakage_ratio(
    target: np.ndarray,
    others: list[np.ndarray],
) -> float:
    target_signal = mono(target).astype(np.float64)
    target_signal -= np.mean(target_signal)
    target_norm = float(np.linalg.norm(target_signal))
    if target_norm <= 1e-12:
        return 0.0
    maximum = 0.0
    for other in others:
        count = min(len(target_signal), len(other))
        other_signal = mono(other[:count]).astype(np.float64)
        other_signal -= np.mean(other_signal)
        target_slice_norm = float(np.linalg.norm(target_signal[:count]))
        other_norm = float(np.linalg.norm(other_signal))
        if target_slice_norm <= 1e-12 or other_norm <= 1e-12:
            continue
        correlation = abs(
            float(
                np.dot(target_signal[:count], other_signal)
                / (target_slice_norm * other_norm)
            )
        )
        maximum = max(maximum, correlation)
    return maximum
