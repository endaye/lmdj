# LMDJ 标记页

`demos/` 下的独立静态站。不是产品构建，也不进 Core。

三页：

- 标记：Creator `LogoIcon` 的四块矢量，原路径，不重绘。
- 乐器：这四块对应的四个工作面。
- 图标：Apple App 图标的标准尺寸，网页主屏幕那一档，以及网站标签页图标。

## 尺寸

| 用途 | 尺寸 | 文件 |
| --- | --- | --- |
| App Icon | 1024×1024 | `icon-1024.png` |
| apple-touch-icon | 180×180 | `apple-touch-icon.png` |
| 矢量 | viewBox `0 0 80 80` | `mark.svg` |
| 标签页 | 32×32 与 16×16 | `favicon.svg`、`favicon.ico` |

1024 是 Xcode 和 App Store 现在要求的那一张。文件是直角、不透明的 RGB PNG，圆角留给系统遮罩。180 是网页加到主屏幕时的那一档，由同一张 `icon.svg` 光栅化。标记在 1024 画布上放大 8 倍，四边留 192px。标签页用同一组路径，画布收到 32，四边留 2，再光栅成 32 与 16 收进 `favicon.ico`。`favicon-32.png` 和 `favicon-16.png` 是这两档的原图，页面按实际像素展示。

路径来自 `apps/creator-web/src/components/hardware_icons.tsx` 的 `LogoIcon`。产品代码不引用这个目录。

## 本地打开

```bash
python3 -m http.server 4179 --directory demos/lmdj-mark
```

然后打开 `http://127.0.0.1:4179/`。

矢量改了以后，在仓库根目录重渲：

```bash
python3 demos/lmdj-mark/tools/render_icon.py
python3 demos/lmdj-mark/test/check_mark.py
```

`render_icon.py` 需要本机的 `rsvg-convert`。检查脚本只读已提交的 SVG 和 PNG。
