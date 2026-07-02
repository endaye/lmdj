from dataclasses import dataclass, field


@dataclass
class PipelineConfig:
    # 全局
    sample_rate: int = 44100
    bars: int = 4                      # loop 小节数
    beats_per_bar: int = 4
    grid_per_beat: int = 4             # 16 分音符网格
    max_samples: int = 6

    # 阶段2 分轨
    demucs_model: str = "htdemucs_ft"  # --fast 时换 htdemucs
    vocals_strategy: str = "merge"     # merge: 并进旋律轨 / drop: 丢弃

    # 阶段3 loop
    n_candidate_windows: int = 5       # 验收不达标时可重试的候选窗口数
    crossfade_ms: float = 8.0
    bpm_hint: float | None = None      # 生成端固定了 BPM 时直接传进来
    max_bpm: float = 130.0             # 超过则视为倍频误检，折半重测
    max_loop_seconds: float | None = None  # loop 时长上限：拍数 16→8→4→2 折半直到塞进去

    # 阶段4 切片
    drum_clusters: int = 3             # 聚类质量差时自动降到 2
    min_cluster_hits: int = 2
    silhouette_floor: float = 0.05
    oneshot_max_sec: float = 0.6
    oneshot_fade_ms: float = 30.0
    gate_db: float = -48.0             # one-shot 门限降噪
    melody_max_samples: int = 2

    # 阶段5 MIDI / lane 约定（pitch ↔ 键位）
    lane_pitches: dict = field(default_factory=lambda: {
        "kick": 36, "snare": 38, "hat": 42,
        "drum_low": 36, "drum_high": 42,   # 降级 2 键位时
        "bass": 48, "melody_a": 50, "melody_b": 52,
        "loop_a": 60, "loop_b": 62, "loop_c": 64,   # ABC loop 模式
        "loop_d": 65, "loop_e": 67, "loop_f": 69,   # DEF 无鼓 loop 模式
        "loop_g": 71, "loop_h": 72, "loop_i": 74,   # 再切一组
        "loop_j": 76, "loop_k": 77, "loop_l": 79,   # 又一组
    })

    # 阶段6 验收
    similarity_threshold: float = 0.50
    long_sample_corr_threshold: float = 0.45
