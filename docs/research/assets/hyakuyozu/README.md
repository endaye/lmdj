# 百様図运行画面截图（研究证据）

本目录的图片是 [大丸松坂屋百貨店「百様図」官网](https://www.daimaru-matsuzakaya.com/vi/en/)
的实时运行画面，供
[`../../2026-09-02-hyakuyozu-paper-layer-visual-technology-study.md`](../../2026-09-02-hyakuyozu-paper-layer-visual-technology-study.md)
§3.8 引用。

## 版权与用途边界

画面内容的版权属于大丸松坂屋百貨店、日本デザインセンター与 mount inc.。这些图
只作为研究引用证据存在：

- 不得进入 LMDJ 产品、宣传物、Architecture Portal 或 Creator 设计标本；
- 不得裁出其中的纸张纹理、图案、Logo 或文案复用；
- 若仓库开源，这一目录属于「第三方作品的研究引用」，需要与源码许可分开说明。

## 抓取环境

| 项 | 值 |
|---|---|
| 日期 | 2026-09-02 |
| 驱动 | Playwright 1.62.1（`tests/platform/web/node_modules`），Chromium 无头 |
| WebGL | SwiftShader 软件 WebGL2（`--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader`） |
| 桌面视口 | 1440 × 810，deviceScaleFactor 1 |
| 手机视口 | 375 × 639，deviceScaleFactor 2，`hasTouch` / `isMobile`，iPhone Safari UA |
| 输出 | JPEG 质量 80–82；对照图裁切自 1440 × 810 PNG 原图 |

页面把 `<html>` 标成 `no3DAccel`，但该 class 在内联 CSS 与 `main.js` 中都没有消费者，
渲染管线与真机相同。软件渲染下 `requestAnimationFrame` 约 149 ms 一帧，所以这些图
只能证明静帧画面，不能证明帧率或节拍。

## 站点自带的 URL 开关

`main.js` 读取 URL 查询键名（不看值），并存入 `sessionStorage.query-stored-keys`：

| 键 | 作用 |
|---|---|
| `page=N` | 直接跳到第 N 段（`gotoDirect`），跳过入口；13 段一循环 |
| `noAuto` | 段结束后不自动推进 |
| `noBgm` | 不播放背景音乐 |
| `albedo` | 全屏合成着色器以 `IS_ALBEDO=1` 编译，直接输出 gAlbedo，跳过阴影 |
| `noText` | 不绑定文字贴图 |
| `detail` / `detailBag` | 进入后直接打开 About Hyakuyo / About shopping bags 模态 |
| `hq` | 阴影图 4096²（默认桌面 2048²） |
| `helper` / `noNoise` / `skip` / `first` / `fps` / `device` / `typo` / `debug` | 调试与工具开关，本研究未依赖 |

## 文件清单

| 文件 | 抓取方式 |
|---|---|
| `pc-00-splash.jpg` | 桌面，`/vi/en/`，加载后等待 4 s |
| `pc-01.jpg` … `pc-12.jpg` | 桌面，`?page=N&noAuto&noBgm`，加载后等待 6.5 s |
| `pc-03-element1-baseline.jpg` | 桌面，`?page=3&noAuto&noBgm`，裁切 780 × 520 @ (330, 40) |
| `pc-03-element1-albedo-only.jpg` | 同上加 `&albedo` |
| `pc-03-element1-text-baseline.jpg` | 桌面，`?page=3&noAuto&noBgm`，裁切 780 × 300 @ (250, 340) |
| `pc-03-element1-text-notext.jpg` | 同上加 `&noText` |
| `pc-03-element1-hover.jpg` | 桌面，`?page=3`，鼠标移到 (860, 300) 后等待 2.5 s，同上裁切 |
| `pc-03-element1-press.jpg` | 同上，再按下左键 0.9 s |
| `pc-03-element1-drag.jpg` | 同上，按下后 30 步移到 (1100, 420) |
| `pc-modal-about.jpg` | 桌面 1440 × 2400 视口，`?detail&noBgm&noAuto`，缩到 1080 宽 |
| `pc-modal-bags.jpg` | 桌面 1440 × 2400 视口，`?detailBag&noBgm&noAuto`，缩到 1080 宽 |
| `sp-00-splash.jpg` | 手机，`/vi/en/?noBgm` |
| `sp-03-touch-0-before.jpg` | 手机，`?page=3&noAuto&noBgm`，加载后等待 6.5 s |
| `sp-03-touch-1-during.jpg` | 同上，CDP `Input.dispatchTouchEvent`：touchStart (190, 300)，24 次 touchMove 每步 (−5, +4) px、间隔 16 ms，停 150 ms 后截图 |
| `sp-03-touch-3-release-1750ms.jpg` | 同上，touchEnd 后 1.75 s |

## 复现要点

- 用仓库现有的 Playwright 依赖，不需要新增包：
  `import { chromium } from 'tests/platform/web/node_modules/@playwright/test/index.mjs'`。
- 生产包的 `logger` / `debug` 覆盖层是空实现，不能用来读运行状态；段落归属靠 `?page=N`
  与画面本身判断。
- 手机端 `page.click('.js_view_startButton')` 会因按钮无尺寸而超时；用 `?page=N` 跳过入口。
- 不同次加载同一段时，段内 `genri` 动画进度不同，对照图会有孔形与位置差异。
