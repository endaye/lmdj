# Suno 输入音频语料

这里存放用于 LMDJ 本地人工冒烟、真实端到端和音频质量回归的 Suno MP3 输入。它们不是自动化测试 fixture，也不属于冻结的 `references/demos/` 源码边界。

MP3 默认被 Git 忽略；仓库只跟踪本说明。若将来要把其中一小部分升级为团队共享的稳定评测集，应先确认使用许可，再经 Git LFS 提交经过筛选的曲目，不要提交重复 ZIP。

## 本地目录

```text
testdata/audio/suno/
├── boom-bap/
│   ├── boom-bap-01.mp3
│   └── boom-bap-02.mp3
├── city-pop/
│   ├── city-pop-01.mp3
│   └── city-pop-02.mp3
├── g-funk/
│   ├── g-funk-01.mp3
│   ├── g-funk-02.mp3
│   ├── g-funk-03.mp3
│   └── g-funk-04.mp3
└── jazzy-hip-hop/
    ├── jazzy-hip-hop-01.mp3
    ├── jazzy-hip-hop-02.mp3
    ├── jazzy-hip-hop-03.mp3
    └── jazzy-hip-hop-04.mp3
```

## 原文件名映射

| 当前路径 | 原文件名 | 时长 |
| --- | --- | ---: |
| `boom-bap/boom-bap-01.mp3` | `boombap1.mp3` | 02:07 |
| `boom-bap/boom-bap-02.mp3` | `boombap2.mp3` | 01:57 |
| `city-pop/city-pop-01.mp3` | `citypop2.mp3` | 02:32 |
| `city-pop/city-pop-02.mp3` | `citypop3.mp3` | 03:01 |
| `g-funk/g-funk-01.mp3` | `G-funk1.mp3` | 01:22 |
| `g-funk/g-funk-02.mp3` | `G-funk3.mp3` | 02:15 |
| `g-funk/g-funk-03.mp3` | `G-funk4.mp3` | 02:24 |
| `g-funk/g-funk-04.mp3` | `G-funk5.mp3` | 01:22 |
| `jazzy-hip-hop/jazzy-hip-hop-01.mp3` | `jazzy hiphop1.mp3` | 01:40 |
| `jazzy-hip-hop/jazzy-hip-hop-02.mp3` | `jazzy hiphop2.mp3` | 01:45 |
| `jazzy-hip-hop/jazzy-hip-hop-03.mp3` | `jazzy hiphop3.mp3` | 02:04 |
| `jazzy-hip-hop/jazzy-hip-hop-04.mp3` | `jazzy hiphop4.mp3` | 02:19 |

## 用法

任选一首作为真实输入，例如：

```bash
workers/audio/.venv/bin/lmdj-audio-worker run \
  testdata/audio/suno/boom-bap/boom-bap-01.mp3
```
