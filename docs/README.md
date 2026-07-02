# LMDJ Docs

这里放产品、原型和跨项目草案。运行与管线使用文档放在对应代码目录 `lmdj-song-pipeline/` 内。

## 文档

- [lmdj-web-prototype-spec.md](lmdj-web-prototype-spec.md)：2026-07-02 收到的 V1 web prototype PRD 素材，当前仅作脑暴参考。

## 当前讨论素材

这份 PRD 素材提出的 web prototype 链路是：

```text
Prompt parameters
  -> live song-pipeline generation
  -> samples + chart.mid + lanes.json + report.json
  -> Playable Patch object
  -> Z X N M guided performance runtime
```

静态包只作为开发 fixture、不能在主流程里悄悄替代失败的实时生成或管线运行，是该素材中的重要约束之一；是否进入最终方案仍待评审。
