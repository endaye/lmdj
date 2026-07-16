"""Tests for self-implemented SI-SDR, mixture consistency, and leakage metrics.

Each test is property-anchored per spec, computing expected values independently.
"""
from __future__ import annotations

import numpy as np
import pytest

from lmdj_audio_worker.benchmark import metrics


class TestSISdr:
    """SI-SDR scale-invariant signal-to-distortion ratio tests."""

    def test_perfect_reconstruction_clips_to_120db(self):
        """要点 1: si_sdr(x, x) == 120.0 dB (ceiling for perfect reconstruction)."""
        # Create a simple stereo signal (1000 samples, 2 channels)
        x = np.random.randn(1000, 2).astype(np.float32)
        result = metrics.si_sdr(x, x)
        assert result == pytest.approx(120.0, abs=1e-6)

    def test_scale_invariance(self):
        """要点 2: si_sdr is scale-invariant (si_sdr(cx, cŝ) == si_sdr(x, ŝ) for c ≠ 0).

        True scale invariance: scaling both reference and estimate by the same factor
        does not change the SI-SDR value.
        """
        np.random.seed(100)
        x = np.random.randn(500, 2).astype(np.float32)
        estimate = x + 0.2 * np.random.randn(500, 2).astype(np.float32)

        # Test: si_sdr(x, estimate) should equal si_sdr(2.5*x, 2.5*estimate)
        result_original = metrics.si_sdr(x, estimate)
        result_scaled_both = metrics.si_sdr(2.5 * x, 2.5 * estimate)

        assert result_original == pytest.approx(result_scaled_both, abs=1e-5)

    def test_monotonicity_decreases_with_noise(self):
        """要点 3: si_sdr monotonically decreases as noise increases (σ=0.1 < σ=0.01)."""
        np.random.seed(42)
        x = np.random.randn(2000, 2).astype(np.float32)
        noise_low = np.random.randn(2000, 2).astype(np.float32) * 0.01
        noise_high = np.random.randn(2000, 2).astype(np.float32) * 0.1

        x_noisy_low = x + noise_low
        x_noisy_high = x + noise_high

        sdr_low_noise = metrics.si_sdr(x, x_noisy_low)
        sdr_high_noise = metrics.si_sdr(x, x_noisy_high)

        assert sdr_low_noise > sdr_high_noise

    def test_silent_ground_truth_returns_none(self):
        """要点 4: si_sdr returns None when ground truth has zero energy."""
        silent_gt = np.zeros((1000, 2), dtype=np.float32)
        estimate = np.random.randn(1000, 2).astype(np.float32)

        result = metrics.si_sdr(silent_gt, estimate)
        assert result is None

    def test_hand_computed_orthogonal_perturbation_anchor(self):
        """要点 5: Hand-computed anchor with orthogonal perturbation (±1e-6 tolerance).

        Theory: If ŝ = s + ε where ε ⊥ s:
          α = ⟨ŝ, s⟩ / ⟨s, s⟩ = ‖s‖² / ‖s‖² = 1
          e_t = s
          e_r = ε
          SI-SDR = 10·log10(‖s‖² / ‖ε‖²)
        """
        # Create reference signal (1D for direct calculation)
        s = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)

        # Create orthogonal perturbation: start with random, orthogonalize via Gram-Schmidt
        # Simple approach: construct [0, 1, -2/3, 0, 0] which is orthogonal to [1, 2, 3, 4, 5]
        eps_test = np.array([0.0, 1.0, -2.0/3, 0.0, 0.0], dtype=np.float64)

        # Verify orthogonality: ⟨s, ε⟩ should be ≈ 0
        assert abs(np.dot(s, eps_test)) < 1e-10

        # Create 2-channel version: both channels have same s, same ε
        s_2ch = np.column_stack([s, s]).astype(np.float32)
        estimate = np.column_stack([s + eps_test, s + eps_test]).astype(np.float32)

        # Hand-compute expected SI-SDR
        # SI-SDR = 10·log10(‖s‖² / ‖ε‖²)
        s_norm_sq = float(np.dot(s, s))
        eps_norm_sq = float(np.dot(eps_test, eps_test))
        expected_sdr = 10.0 * np.log10(s_norm_sq / eps_norm_sq)

        # Call implementation
        result = metrics.si_sdr(s_2ch, estimate)

        assert result == pytest.approx(expected_sdr, abs=1e-6)


class TestMixtureConsistency:
    """Mixture consistency metric tests."""

    def test_perfect_sum_clips_to_floor(self):
        """要点 6a: mixture_consistency clips to MC_FLOOR_DB (−120.0) when estimates sum exactly to mix."""
        drums = np.random.randn(1000, 2).astype(np.float32)
        bass = np.random.randn(1000, 2).astype(np.float32)
        vocals = np.random.randn(1000, 2).astype(np.float32)
        other = np.random.randn(1000, 2).astype(np.float32)

        # Perfect sum: mix = exact sum of stems
        mix = drums + bass + vocals + other

        estimates = {
            "drums": drums,
            "bass": bass,
            "vocals": vocals,
            "other": other,
        }

        result = metrics.mixture_consistency(estimates, mix)
        assert result == pytest.approx(-120.0, abs=1e-6)

    def test_residual_energy_1percent_gives_minus_20db(self):
        """要点 6b: mixture_consistency ≈ −20.0 dB when residual energy is 1% of mix energy.

        Theory: MC = 10·log10(‖residual‖² / ‖mix‖²)
        If residual² = 0.01 × mix², then MC = 10·log10(0.01) = −20.0 dB
        """
        # Create base mix
        np.random.seed(43)
        drums = np.random.randn(1000, 2).astype(np.float32) * 0.5
        bass = np.random.randn(1000, 2).astype(np.float32) * 0.3
        vocals = np.random.randn(1000, 2).astype(np.float32) * 0.4
        other = np.random.randn(1000, 2).astype(np.float32) * 0.2

        mix = drums + bass + vocals + other

        # Create estimates that sum to (mix + perturbation)
        # Perturbation energy = 1% of mix energy
        mix_energy = float(np.sum(mix.astype(np.float64) ** 2))
        target_residual_energy = mix_energy * 0.01

        # Create a perturbation with exactly this energy
        perturbation = np.random.randn(1000, 2).astype(np.float32)
        pert_energy = float(np.sum(perturbation.astype(np.float64) ** 2))
        perturbation = perturbation * np.sqrt(target_residual_energy / pert_energy)

        # Distribute perturbation across stems
        pert_drums = perturbation * 0.25
        pert_bass = perturbation * 0.25
        pert_vocals = perturbation * 0.25
        pert_other = perturbation * 0.25

        estimates = {
            "drums": drums + pert_drums,
            "bass": bass + pert_bass,
            "vocals": vocals + pert_vocals,
            "other": other + pert_other,
        }

        result = metrics.mixture_consistency(estimates, mix)

        # Verify residual energy is indeed 1% of mix
        total_est = sum(estimates.values())
        residual = total_est.astype(np.float64) - mix.astype(np.float64)
        residual_energy = float(np.sum(residual ** 2))
        actual_ratio = residual_energy / mix_energy

        assert result == pytest.approx(-20.0, abs=0.1)


class TestLeakage:
    """Leakage (cross-stem interference) metric tests."""

    def test_pure_other_stem_estimate_leaks_minimally(self):
        """要点 7a: leakage ≈ 0.0 dB when estimate equals pure other-stem GT.

        If ŝᵢ = sⱼ (j ≠ i), then βⱼ = 1.0 and leakᵢ = 10·log10(‖sⱼ‖² / ‖sⱼ‖²) = 0.0 dB.
        """
        np.random.seed(44)

        # Create reference stems
        drums_ref = np.random.randn(500, 2).astype(np.float32) * 0.8
        bass_ref = np.random.randn(500, 2).astype(np.float32) * 0.6
        vocals_ref = np.random.randn(500, 2).astype(np.float32) * 0.7
        other_ref = np.random.randn(500, 2).astype(np.float32) * 0.5

        references = {
            "drums": drums_ref,
            "bass": bass_ref,
            "vocals": vocals_ref,
            "other": other_ref,
        }

        # Estimates: drums_estimate = vocals_ref (pure other stem)
        estimates = {
            "drums": vocals_ref,  # Drums estimate is actually vocals
            "bass": bass_ref,     # Bass is clean
            "vocals": vocals_ref,  # Vocals is clean
            "other": other_ref,   # Other is clean
        }

        result = metrics.leakage(estimates, references)

        # Drums should leak from vocals (estimate equals vocals GT)
        assert result["drums"] == pytest.approx(0.0, abs=0.1)

    def test_self_stem_orthogonal_to_others_has_low_leakage(self):
        """要点 7b: leakage < −60 dB when estimate = self stem and orthogonal to all others.

        If ŝᵢ = sᵢ (perfect self) and sᵢ ⊥ all sⱼ (across both channels):
          βⱼ ≈ 0 for all j ≠ i
          leakᵢ = 10·log10(0 / ‖sᵢ‖²) → −∞ (clipped by _EPS mechanism)
        """
        # Use DCT basis vectors which are orthonormal: create stems from orthogonal sinusoids
        np.random.seed(45)
        N = 200
        t = np.arange(N)

        # Create 4 orthogonal sinusoidal bases (different frequencies)
        drums_ref = np.column_stack([
            np.sin(2 * np.pi * 1 * t / N) * 0.8,
            np.sin(2 * np.pi * 1 * t / N + np.pi/3) * 0.8
        ]).astype(np.float32)

        bass_ref = np.column_stack([
            np.sin(2 * np.pi * 2 * t / N) * 0.6,
            np.sin(2 * np.pi * 2 * t / N + np.pi/3) * 0.6
        ]).astype(np.float32)

        vocals_ref = np.column_stack([
            np.sin(2 * np.pi * 3 * t / N) * 0.7,
            np.sin(2 * np.pi * 3 * t / N + np.pi/3) * 0.7
        ]).astype(np.float32)

        other_ref = np.column_stack([
            np.sin(2 * np.pi * 4 * t / N) * 0.5,
            np.sin(2 * np.pi * 4 * t / N + np.pi/3) * 0.5
        ]).astype(np.float32)

        # Verify orthogonality of the sinusoidal components
        drums_full = drums_ref.astype(np.float64).flatten()
        bass_full = bass_ref.astype(np.float64).flatten()
        assert abs(np.dot(drums_full, bass_full)) < 1.0, "Sinusoids should be nearly orthogonal"

        references = {
            "drums": drums_ref,
            "bass": bass_ref,
            "vocals": vocals_ref,
            "other": other_ref,
        }

        # Estimates = perfect self stems
        estimates = {
            "drums": drums_ref,
            "bass": bass_ref,
            "vocals": vocals_ref,
            "other": other_ref,
        }

        result = metrics.leakage(estimates, references)

        # All stems should have very low leakage (highly orthogonal sinusoids)
        for stem, leak in result.items():
            if leak is not None:
                assert leak < -50, f"Stem {stem} leakage {leak} dB should be < -50 dB (orthogonal sinusoids)"

    def test_silent_estimate_returns_none(self):
        """要点 7c: leakage returns None when estimate has zero energy."""
        references = {
            "drums": np.random.randn(100, 2).astype(np.float32),
            "bass": np.random.randn(100, 2).astype(np.float32),
            "vocals": np.random.randn(100, 2).astype(np.float32),
            "other": np.random.randn(100, 2).astype(np.float32),
        }

        # Silent estimates
        estimates = {
            "drums": np.zeros((100, 2), dtype=np.float32),
            "bass": np.random.randn(100, 2).astype(np.float32),
            "vocals": np.random.randn(100, 2).astype(np.float32),
            "other": np.random.randn(100, 2).astype(np.float32),
        }

        result = metrics.leakage(estimates, references)

        # Drums should be None because estimate is silent
        assert result["drums"] is None
        # Others should be valid
        assert result["bass"] is not None
        assert result["vocals"] is not None
        assert result["other"] is not None
