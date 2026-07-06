# LMDJ song-pipeline — 安装与使用手册

把一首成品音乐（生成的 / 老唱片 / 任意 mp3）全自动拆成 **≤6 个 samples + MIDI 谱面**，
再按规则重新演奏出 render。这份文档覆盖：迁移到新机器需要装什么、每一步怎么跑、
以及所有调过的参数在哪里改。

---

## 1. 这套工作流是什么

```
来源音频
 │  ① 生成   generate.py     MusicGen 固定 BPM 出 lofi（可选，也可直接喂现成曲）
 │  ① 取料   yt-dlp / archive.org   YouTube 歌单、Great 78 老唱片
 ▼
 ② 分轨   stems.py        Demucs → drums / bass / melody
 ③ 切 loop loop_finder.py  三路投票找真 downbeat + 真 4 拍 guard + 切口干净度打分
 ④ 切片   slicer.py        鼓→kick/snare/hat one-shot；bass/melody→长样本
 ⑤ MIDI   sequencer.py     16 分网格量化 → chart.mid + lanes.json
 ⑥ 验收   validate.py      重渲染比对，不达标自动换窗口重试
 ▼
出包 output/{song_id}/  samples/*.wav + chart.mid + lanes.json + render
```

之上还有几种**成品玩法脚本**（scripts/）：ABC / DEF 多 loop 模式、鼓变奏、
boom bap 重渲染、鼓音色 A/B。详见第 5、6 节。

---

## 2. 系统要求与安装

### 2.1 必须先装的系统工具

| 工具 | 用途 | macOS | Ubuntu/Debian |
| --- | --- | --- | --- |
| **Python ≥3.10** | 运行环境（开发用 3.11） | `brew install python@3.11` | `apt install python3.11 python3.11-venv` |
| **ffmpeg** | Demucs/librosa 读写音频，**必须** | `brew install ffmpeg` | `apt install ffmpeg` |
| **yt-dlp** | 从 YouTube 取料（可选） | `brew install yt-dlp` | `pipx install yt-dlp` |

### 2.2 Python 依赖（虚拟环境）

```bash
cd references/demos/lmdj-song-pipeline
python3 -m venv .venv
.venv/bin/pip install --upgrade pip

# 核心管线（分轨/切loop/切片/MIDI/验收/API）
.venv/bin/pip install -e .

# 需要 MusicGen 生成（阶段1）再装：
.venv/bin/pip install -e ".[generate]"

# 需要 yt-dlp 作为 python 包再装（也可用系统版）：
.venv/bin/pip install -e ".[fetch]"
```

核心依赖（写在 `pyproject.toml`）：`numpy<2, soundfile, librosa, scikit-learn,
pretty_midi, demucs, torch, torchaudio, fastapi, uvicorn, python-multipart`。
**注意 numpy 必须 <2**（demucs/numba 兼容性）。

### 2.3 模型权重（首次运行自动下载，需联网）

- **Demucs**：`htdemucs_ft`（4 模型 bag，准）约 320MB / `htdemucs`（单模型，快 4 倍）约 80MB。
  存到 `~/.cache/torch/hub/checkpoints/`。**下载中断会留坏文件报 "invalid hash"，删掉重下即可。**
- **MusicGen-small**（仅生成用）约 440MB，存到 `~/.cache/huggingface/`。

迁移时如果想免去重新下载，把这两个 cache 目录一起拷过去。

### 2.4 验证安装

```bash
.venv/bin/python -m pytest tests/ -q          # 6 个冒烟测试应全过
.venv/bin/song-pipeline --help
```

---

## 3. 快速开始（出第一个包）

```bash
# A. 有现成 mp3/wav：跑完整管线
.venv/bin/song-pipeline run 你的歌.mp3 --song-id mysong --fast

# B. 没有素材，让 MusicGen 生成一首再跑：
.venv/bin/song-pipeline gen --bpm 85 --style "lofi hiphop beat" --seconds 30 --seed 42 --fast --run

# 输出在 output/mysong/：samples/*.wav + chart.mid + lanes.json + report.json
#   loop_preview.wav   = 切出的原 loop
#   render_preview.wav = 用 samples+MIDI 重渲染（验收听感）
```

`--fast` = 用 htdemucs 单模型分轨，速度快 4 倍，本地调试强烈建议带上。

---

## 4. CLI 命令一览

```bash
song-pipeline run <音频> [--song-id X] [--fast] [--bars N] [--max-loop-seconds S] [--abc]
song-pipeline gen [--bpm 85] [--style "..."] [--seconds 30] [--seed N] [--fast] [--run]
song-pipeline batch <目录> [--fast]              # 跑目录下所有音频，出合格率报告
song-pipeline serve [--host] [--port 8000]       # FastAPI 服务
```

**FastAPI 接口**（`serve` 起服务后）：
```bash
curl -F file=@input.mp3 http://localhost:8000/songs       # → {"song_id": ...}
curl http://localhost:8000/songs/{id}                     # 查状态/report
curl -O http://localhost:8000/songs/{id}/package          # 下载谱面包 zip
```

---

## 5. 取料与多 loop 玩法脚本（scripts/）

> 这些是在基础管线之上的“切法”脚本，逐步调出来的。都直接 `.venv/bin/python scripts/xxx.py` 跑。

### 5.1 从来源取料

```bash
# YouTube 歌单里某首
yt-dlp -x --audio-format mp3 --audio-quality 0 -o "input_yt/%(title)s.%(ext)s" "<视频URL>"

# archive.org Great 78 老唱片（公有领域，可自由下载）
curl -s "https://archive.org/advancedsearch.php?q=collection%3Ageorgeblood+AND+subject%3A%22swing%22&fl%5B%5D=identifier&rows=15&output=json"
curl -sL "https://archive.org/download/<identifier>/<文件名>.mp3" -o input_78/x.mp3
```

### 5.2 ABC / DEF 多 loop 模式

- **ABC**（`song-pipeline run ... --abc`）：切 3 个 loop——A=1小节、B/C=半小节，
  谱面 **A-A-A-BC** 走完 4 小节。B 只从原曲前半小节取、C 只从后半取（节拍语法对齐）。
- **DEF**（`scripts/make_def_package.py`）：3 个**无鼓** loop（从 bass+melody 切）+
  鼓单独成 kick/snare/hat one-shot，chart.mid 同时触发 loop 和鼓。真正的 6-sample 包。

```bash
# DEF 出包：python make_def_package.py <song_dir> [seed] [字母组] [tag]
.venv/bin/python scripts/make_def_package.py output/mysong 2 def def
# 再切一组不重叠的（自动避让，sidecar 记录已切窗口）：
.venv/bin/python scripts/make_def_package.py output/mysong 5 ghi ghi
```

避让机制：每次切的窗口写进 `output/<song>/loop_windows.json`，下次自动跳开，不会撞车。

### 5.3 鼓玩法

```bash
# 鼓变奏（原鼓音色，按规则做变奏，全落16分网格）
.venv/bin/python scripts/render_drumvar.py output/mysong <seed>

# 鼓替换（把鼓换成另一首歌切出的 one-shot，bass/melody 不变）
.venv/bin/python scripts/render_drumswap.py output/mysong output/鼓源song

# boom bap 重渲染（复用某组 loop，鼓换成基本/groove boom bap）
.venv/bin/python scripts/rerender_boombap.py output/mysong <源tag> <输出tag>
```

---

## 6. 参数调制总表 ⭐

> 所有“感觉”都是这里调出来的。改完重跑对应脚本即可。

### 6.1 全局 / 切片 — `song_pipeline/config.py` (`PipelineConfig`)

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `bars` | 4 | loop 小节数。CLI `--bars 1` 可覆盖（切 1 小节 loop） |
| `max_samples` | 6 | 每首歌总样本预算上限 |
| `demucs_model` | htdemucs_ft | 分轨模型；`--fast` 时换 htdemucs |
| `vocals_strategy` | merge | 人声并进旋律(merge) / 丢弃(drop) |
| `n_candidate_windows` | 5 | 验收不达标时最多重试几个候选窗口 |
| `crossfade_ms` | 8.0 | loop 首尾无缝化的 crossfade 时长 |
| `bpm_hint` | None | 生成端固定了 BPM 就传入，跳过倍频纠错 |
| `max_bpm` | 130 | 超过视为倍频误检，BPM 自动折半重测 |
| `max_loop_seconds` | None | loop 时长上限，拍数 16→8→4→2 折半塞进去 |
| `drum_clusters` | 3 | 鼓聚 kick/snare/hat；质量差自动降到 2 键位 |
| `silhouette_floor` | 0.05 | 聚类质量阈值，低于此降级 2 键位 |
| `oneshot_max_sec` | 0.6 | one-shot 最长截断 |
| `oneshot_fade_ms` | 30 | one-shot 尾部 fade |
| `gate_db` | -48 | one-shot 门限降噪（去分轨残留） |
| `melody_max_samples` | 2 | 旋律最多切几段长样本 |
| `lane_pitches` | dict | pitch ↔ 键位/loop 名映射（游戏端 sample-map 对齐处） |
| `similarity_threshold` | 0.50 | 验收阈值，render 与原 loop 频谱相似度低于此则 rejected |

### 6.2 切 loop 找准“第一拍” — `song_pipeline/loop_finder.py`

切真实老唱片认可的配方，三件事叠加（`detect_beats` + `find_loop_windows`）：

1. **真 downbeat 三路投票**（`detect_beats`）：和声变化(权重 **0.4**) + 贝斯根音(**0.3**) +
   kick 低频(**0.3**)。纯 kick 会被反拍/弱起骗，和声变化是关键信号。
2. **真 4 拍保证**：窗口内拍距偏离中位数 **≤6%**、总长偏离名义 BPM **≤10%**，否则剔除。
3. **切口干净度打分**（`find_loop_windows` 的 `score`）：
   `0.25·能量稳定 + 0.25·首尾频谱相似 + 0.1·onset密度 + 0.2·head_attack + 0.12·tail_quiet + 0.08·head_quiet`
   —— head_attack=小节头有清晰音头，tail/head_quiet=边界前无音延续（防 click）。

### 6.3 鼓 one-shot 切片判据 — `song_pipeline/slicer.py` (`cut_oneshots_by_label`)

**不信任分类标签**（demucs 鼓轨 snare/hat 高频都强会贴反），按相对特征各挑一发：

- **kick** = `low − 0.5·high`（低频最强）
- **hat** = `high + 质心norm + 短促度`（最亮、最短）
- **snare** = `mid + 0.4·high − 1.0·low − 0.5·质心norm − 0.3·短促度`
  （中频 body 强、**低频不能主导**否则选成 kick、暗于 hat）

调好的目标频谱参考：kick 质心~860Hz、snare ~4-5kHz/low<0.1/有body、hat ~10kHz/极短。
换 snare 音色：按 snare 打分排序看候选数，导出前几名 A/B，挑中的拷成 `samples/snare.wav`。

### 6.4 鼓变奏规则 — `scripts/render_drumvar.py`

A-A-A-BC 结构下（`build_a_bar` / `build_bar4_half`）：

- **前三小节**：kick **必须开第一拍**（原采样没有就补）；snare **锁死 2、4 拍**；
  hat 原样；变奏只在 kick——可加密，但新 kick 离已有 kick **≥2 个 16 分**。
- **末小节**：snare 位置可挪（可顶掉同位 hat），可加 fill。
- **所有鼓击严格落 16 分网格**（量化）。变奏要**克制**，每小节一两处即可。

### 6.5 boom bap — `scripts/rerender_boombap.py`

最基本写法（`boombap_bar`）：kick 落 1/3 拍、snare 落 2/4 拍、hat 八分音符。
`main()` 三个味道开关：

| 参数 | 作用 |
| --- | --- |
| `swing`（0~1，建议 0.5） | 反拍八分 hat 往后挪，做出摇摆。0=直 |
| `ghost_kick`（True/False） | 整小节在 beat 3.5 加一发切分 kick |
| `fill_half_bar`（已内置） | 第四小节后半做 snare 16 分 roll 渐强收尾，替代机械重复 |

调用例（groove 版，不重切鼓沿用现有 snare）：
```python
from rerender_boombap import main
main(Path("output/mysong"), "jkl", "jkl_bb_groove", recut=False, swing=0.5, ghost_kick=True)
```

### 6.6 生成 — `song_pipeline/generate.py`

`song-pipeline gen --bpm N --style "..." --seconds S --seed N`。prompt 模板固定 BPM。
本地 CPU 用 musicgen-small（30s 约数分钟）；云端 GPU 可换 `musicgen-medium/large`
或 ACE-Step，接口不变。环境变量 `SONG_PIPELINE_DEVICE=cuda/cpu/mps` 强制 demucs 设备。

---

## 7. 调音色/找 loop 的工作循环

1. `song-pipeline run 歌.mp3 --fast` 出基础包，听 `render_preview.wav` 和 `loop_preview.wav`。
2. loop 不对（第一拍偏、有弱起、拍不齐）→ 看 6.2，多数是 downbeat 投票或 4 拍 guard 的事。
3. 鼓件混（snare 像 kick / hat 像 snare）→ 看 6.3，调 `cut_oneshots_by_label` 打分权重。
4. 要多 loop / 无鼓 loop → `make_def_package.py`，换字母组+tag 切多组。
5. 鼓太机械 / 太满 → 6.4 变奏 或 6.5 boom bap 的 swing/ghost_kick/fill。
6. 满意了，最终 render 是某个 `render*.wav`，samples/ 是配套素材包。

---

## 8. 迁移 / 分享清单

打包时**排除**：`.venv/`（1GB+，对方重建）、`output/`（生成物）、`input_*/`（素材）、
`__pycache__/`、`.pytest_cache/`。打包命令见随附的 `make_share_zip.sh`。

对方拿到 zip 后：解压 → 第 2 节装环境 → `pytest` 验证 → 第 3 节出第一个包。
模型权重首次跑自动下载（需联网），或随包附上 `~/.cache/torch` 与 `~/.cache/huggingface`。
