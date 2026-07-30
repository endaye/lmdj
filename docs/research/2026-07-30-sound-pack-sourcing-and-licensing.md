# LMDJ Preset / Sound Pack 采购与授权研究

> 更新时间：2026-07-30
>
> 状态：研究与采购准备，不代表批准采购、签约、实现内容商店或改变产品合同
>
> 研究问题：哪里可以取得成套、可商用并可随 LMDJ 分发的 Preset / Sound Pack？

## 1. 结论

LMDJ 可以采购类似 Groovebox 下载扩展包的声音内容，但不能把普通
`royalty-free` Sample Pack、Preset Bank 或 Loop Pack 直接装进产品。

普通零售授权通常只允许购买者使用素材制作和发行音乐，不允许：

- 把原始 Sample、Preset、MIDI 或 Template 交给其他用户；
- 把素材装入另一个音乐软件、虚拟乐器或 Sound Library；
- 把素材重新包装成免费或付费扩展包；
- 把个人、不可转让的授权转成 LMDJ 用户的使用权。

LMDJ 需要的是以下三种路径之一：

1. **定制内容 + OEM / Embedded Redistribution License**：由声音设计公司按
   LMDJ 格式制作，合同明确允许随产品及扩展包分发；
2. **原创委托 + 权利转让或永久许可**：直接委托声音设计师制作，并取得足够的
   修改、分发和终端用户商用权；
3. **CC0 / 可再分发开放素材**：只采用来源和许可证都可验证的素材，保留完整
   Provenance 记录。

当前最可执行的采购方向是：以 **New Loops、Mind Flux、Capsun ProAudio**
作为第一轮询价对象，委托一个小型、原创、可随 LMDJ 分发的试验 Sound Set。
Splice、Loopmasters 等零售商店更适合用于试听、趋势研究和寻找创作者，不适合
直接成为 LMDJ 的供货授权。

## 2. 研究边界与证据等级

本文只研究：

- 音色内容的来源；
- 零售授权与产品内再分发授权的区别；
- 潜在供应商；
- 免费素材的可用性；
- LMDJ 未来采购合同与交付规格。

本文不决定：

- LMDJ 是否要做内容商店；
- Sound Set 是否免费、付费、订阅或一次性购买；
- 是否引入内部 Synth Engine；
- 是否把当前 Pad / Patch 合同扩展成新的公开格式；
- 是否与任何供应商签约。

证据按以下等级标记：

| 等级 | 含义 |
| --- | --- |
| A | 官方许可证、官方条款或官方服务说明 |
| B | 供应商官网公布的客户、项目和能力 |
| C | 基于 A/B 级证据形成的 LMDJ 分析与建议 |
| U | 尚未通过书面合同或供应商确认的事项 |

本文不是法律意见。正式采购前应让熟悉软件、音乐和数字内容授权的律师审阅最终合同。

## 3. 首先区分三种“可商用”

### 3.1 用声音制作商业音乐

购买者可以使用 Sample 或 Preset 创作歌曲，并把完成的歌曲发行到流媒体、影视、
游戏或广告中。这是多数商店所说的：

- `royalty-free`；
- `commercial use`；
- `use in your productions`。

这类授权通常只覆盖完成的音乐作品，不覆盖原始声音的再次分发。

### 3.2 把声音嵌入商业软件

LMDJ 把声音作为可演奏内容交给用户，本质上是在分发原始或近似原始的音频资产。
即使文件经过压缩、加密、切片或改名，只要用户能够在音乐工具中独立触发、调用或
导出，通常仍不能依赖普通音乐制作授权。

LMDJ 至少需要供应商明确授予：

- 在 Web、PWA、Desktop、Mobile 等 LMDJ 产品中嵌入内容；
- 向所有 LMDJ 用户分发或提供下载；
- 作为内置内容、免费扩展包或付费扩展包提供；
- 允许 LMDJ 对素材进行编辑、转码、压缩、切片、Loop 和响度处理；
- 允许终端用户使用该内容创作并商业发行音乐。

### 3.3 把原始声音导出给用户

如果 Creator Export 会把供应商的 Kick、Snare、Loop 或 Multisample 作为独立
WAV 文件交给用户，那么 LMDJ 需要比“应用内嵌入”更强的授权：

- 允许向终端用户分发独立音频资产；
- 允许终端用户在 LMDJ 之外继续使用；
- 说明终端用户能否继续转授权或仅能用于自己的音乐；
- 说明声音是否能进入 DAW 工程、Sample ZIP 或其他开放格式。

这是当前最重要的产品与授权联动点。若供应商不允许独立 Sample 导出，产品可以考虑
只导出用户编排后的 Stem、Loop 或 Mix，而不导出原始 Pack 文件。这个选择必须在
采购前确定，不能在签约后再假设。

## 4. 零售商店授权审查

### 4.1 Splice

**官方事实（A）**

Splice 允许用户把下载的 Sounds 用于新的音乐录音和其他 Creative Works，但官方
条款同时禁止：

- 单独转授权 Sounds；
- 将 Sounds 转让或分发给第三方；
- 把 Sounds 重新分发成新的 Sample Pack；
- 把 Instrument Presets 单独分发或重新组成新的 Pack；
- 以与 Splice 或其授权方竞争的方式使用内容。

**LMDJ 判断（C）**

普通 Splice 下载授权不能支持 LMDJ 内置或销售 Sound Set。Splice 可用于：

- 研究当下流行的声音分类、标签、命名和试听体验；
- 找到适合的声音设计师或厂牌；
- 制作不会公开发布的内部方向参考。

如希望使用特定 Splice 厂牌内容，必须另行与权利人签订书面 OEM 或再分发协议。

### 4.2 Loopmasters / Loopcloud

**官方事实（A）**

Loopmasters 的标准协议把 Audio、Preset 和 Template 授权给原始购买者，允许其
用于音乐作品，但明确规定：

- 授权不可转让；
- 原始或修改后的 Sounds 不得再次销售、授权或分发；
- Preset 和 Template 不得再次销售、授权或分发；
- 不得把内容用于向第三方销售或再授权的竞争产品。

官方同时说明，平台代表的部分第三方厂牌可能有不同条款，存在疑问时应联系平台或
厂牌本身。

**LMDJ 判断（C）**

普通 Loopmasters 订单不能直接成为 LMDJ Pack。它适合用来：

- 发现厂牌、创作者和风格方向；
- 采购仅供内部原型使用的参考内容；
- 寻找愿意单独提供扩展授权的权利人。

### 4.3 Polyend

**官方事实（A）**

Polyend 自己销售 Groovebox / Tracker 相关 Sound Pack，但其内容协议同样限定为
单用户音乐创作用途，禁止分享、分发、转售，以及使用其声音制作新的 Sample Pack、
Preset Collection 或 Sound Library。

协议也提到，若要把声音用于向多方销售或再授权的产品，需要单独安排扩展授权。

**LMDJ 判断（C）**

即使 Sound Pack 来自另一个 Groovebox 厂商，也不表示它可以进入 LMDJ。Polyend
适合作为产品形式参考，不是可直接搬运的内容来源。

## 5. 建议优先联系的供应商

下表中的“适合”只表示其官方能力和履历与需求匹配，不表示标准零售产品已经获得
LMDJ 所需授权。所有候选都必须重新报价和签署书面合同。

| 优先级 | 供应商 | 官方能力与履历 | 适合 LMDJ 的方向 | 证据 |
| --- | --- | --- | --- | --- |
| P0 | New Loops | 提供定制 Loop、Sample、Synth Preset 和 Sound Bank；官网明确提到 Sampler、Drum Machine、Groovebox；公布的项目包括 Elektron、Arturia、Native Instruments、Reason Studios、U-he、Kilohearts | 完整 LMDJ Sound Set、电子乐/Beat Kit、Pattern、Factory Content | A/B |
| P0 | Mind Flux | 提供 Plugin/Hardware Factory Preset、商业扩展包、Sample Pack 和专有未发布乐器内容，并支持 NDA | House、Techno、电子乐、FX 与 Synth-oriented Pack | A/B |
| P1 | Capsun ProAudio | 自建团队制作 Sample、原创 Composition 和 Custom Synth Preset；公布的客户包括 Native Instruments、Novation、Akai、Bitwig、Retronyms | Hip-hop、Trap、现代电子乐、品牌合作 Pack | B |
| P1 | MSXII Sound Design | 提供 WAV Kit、Break、Sample Pack；公布的关联客户包括 Novation、Intua、Akai、Ableton、Native Instruments | Boom-bap、Lo-fi、Hip-hop、MPC 风格 Creator Pack | B |

### 5.1 New Loops

New Loops 是当前最匹配的第一询价对象，因为其官方服务页直接描述了：

- 为新产品或服务提供定制声音；
- 为 Sampler、Drum Machine 和 Groovebox 制作 Loop 与 Sample；
- 制作软件和硬件 Synth Preset / Sound Bank；
- 为多个成熟音乐技术公司交付 Factory Content。

**待确认（U）**

- 是否接受永久、全球、可下载的 LMDJ OEM 授权；
- 是否允许终端用户导出独立 Sample；
- Exclusive、Timed Exclusive 和 Non-exclusive 的价格差异；
- 是否能够同时交付 Pattern、元数据、封面和 Demo。

### 5.2 Mind Flux

Mind Flux 官方明确提供：

- Factory Preset；
- Plugin Launch Content；
- Commercial Expansion Pack；
- Custom Sample Pack；
- Proprietary / Unreleased Instrument Content；
- NDA 项目。

**待确认（U）**

- 是否能够按 LMDJ 自有格式交付，而不是 Serum、Diva、Kontakt 等第三方格式；
- 是否覆盖 LMDJ 需要的鼓组、Bass、Phrase 与 Pattern；
- 是否允许后续把相同制作流程扩展成持续更新的 Creator Pack。

### 5.3 Capsun ProAudio

Capsun 的公开履历与 Groovebox、软件乐器和现代 Beat 内容高度相关，且曾与 Novation、
Akai、Retronyms 等厂商合作。

**待确认（U）**

- 官网没有公布标准 OEM 报价，需要直接询问；
- Splice 上的 Capsun 零售内容仍受 Splice 条款限制，不能因为 Capsun 有厂商合作
  履历就直接下载再分发；
- 需要确认合同签约主体、内容原创保证和可导出边界。

### 5.4 MSXII Sound Design

MSXII 的风格和设备履历适合 Hip-hop / Beat 场景，WAV 交付也比专有 Synth Preset
更容易进入当前 LMDJ Sample / Pad 路线。

**待确认（U）**

- 其标准零售授权是否完全排除软件内再分发；
- 是否接受原创委托或特定 Pack 的扩展授权；
- 是否能提供未进入其他 Sample 商店的独占或窗口期内容。

## 6. 免费和开放素材

### 6.1 VSCO 2 Community Edition

**官方事实（A）**

Versilian Studios 明确把 VSCO 2 Community Edition 以 CC0 发布，并提供：

- 原始 WAV；
- Vanilla SFZ；
- 约 3 GB 的 Chamber Orchestra 素材；
- 允许用户按任意格式重新制作乐器。

**LMDJ 判断（C）**

它是目前证据最清楚的免费候选，可用于：

- 验证 Multisample / Instrument Mapping；
- 制作弦乐、铜管、木管和原声打击乐的内部原型；
- 验证 LMDJ Sound Set 的开放格式。

它不是现成的现代 Beat / Groovebox Pack，也不应该直接承担 LMDJ 的品牌声音身份。
如使用，应优先采用官方提供的 Raw WAV 或 Vanilla SFZ，不应默认第三方衍生版本具有
相同的来源清晰度。

### 6.2 Freesound CC0

**官方事实（A）**

Freesound 每个文件有独立许可证。其 FAQ 说明：

- CC0 基本允许任意使用和再次分发；
- CC BY 要求署名；
- CC BY-NC 不能用于商业用途；
- 用户上传内容仍可能发生错误授权或上传侵权素材；
- 原始素材进入 Content ID 后可能触发第三方 Claim。

**LMDJ 判断（C）**

Freesound 只适合做补充来源，不适合直接批量抓取形成 LMDJ Sound Library。若采用：

1. 只筛选 CC0；
2. 排除 Vocal、知名歌曲、影视、游戏、设备 ROM 和来源不清内容；
3. 保存文件页、作者、许可证、下载日期、原始文件和 SHA-256；
4. 对相似素材做人工听审；
5. 准备替换与下架机制。

### 6.3 GeneralUser GS：许可证宽松但来源风险偏高

**官方事实（A）**

GeneralUser GS 的许可证允许在软件项目中使用和修改 SoundFont，但作者也明确说明：

- 部分 Sample 来自过去互联网上免费提供的其他 SoundFont；
- 无法 100% 确认所有 Sample 的来源；
- 作者本人提示，这种不确定性可能让商业软件开发者担忧。

**LMDJ 判断（C）**

它可以用于内部兼容性测试，但不建议作为 LMDJ 正式商业 Sound Library 的来源。
“允许用于软件”不能替代完整、逐项可追踪的 Sample Provenance。

## 7. LMDJ 应采购什么，而不只是购买什么格式

### 7.1 不建议优先采购第三方 Synth Preset

Serum、Kontakt、Ableton、Omnisphere、Diva、Pigments 等 Preset 通常依赖：

- 特定第三方音源或插件；
- 特定版本的 DSP、Wavetable、Sample 和效果器；
- 第三方软件许可证；
- 不公开或不稳定的 Preset Schema。

即使 Preset 本身可商用，也不代表 LMDJ 能加载、复现或分发其依赖内容。

在 LMDJ 没有确认自有 Synth Engine 和 Preset Schema 前，优先采购以下开放交付：

- 原始 WAV One-shot；
- 可无缝循环的 Phrase / Texture；
- 清晰的 Multisample Mapping；
- MIDI / Pattern 数据；
- 能映射到 LMDJ Sound Role 的元数据；
- 由 LMDJ 自己生成的运行时压缩格式。

### 7.2 建议定义 `LMDJ Sound Set`

这是研究建议，不是已经确认的公开合同。一个 Sound Set 可以包含：

```text
sound-set/
├── manifest.json
├── samples/
│   ├── drums/
│   ├── bass/
│   ├── melodic/
│   ├── vocal/
│   ├── phrase/
│   └── texture/
├── patterns/
├── previews/
├── artwork/
├── provenance/
│   ├── rights.json
│   └── source-files.csv
└── LICENSE.txt
```

建议每个资产至少记录：

- `asset_id`；
- 名称与 Creator；
- Sound Role；
- BPM / Key / Root Note；
- Loop Point；
- 原始采样率、位深和声道；
- Loudness / Peak；
- 原创来源；
- 授权类型与合同版本；
- 是否允许应用外独立导出；
- 是否允许用于用户商业发行；
- 文件 Hash。

Sound Set 应由后续适配器转换成 LMDJ 的稳定产品合同；Web、API 和其他消费者不应直接
读取供应商私有 Manifest。

## 8. 建议的首个试单

第一单的目标不是一次买很多声音，而是验证完整的内容生产、验收、授权和上线流程。

### 8.1 内容范围

建议询价范围：

- 一个明确主题，例如 Modern Hip-hop、Lo-fi、House 或 Electronic；
- 4 套可以映射到当前 Pad 演奏面的 Kit；
- 每套包含 Kick、Snare、Hat、Percussion、Bass、Melodic、Phrase / Texture 等角色；
- 一组可编辑 Pattern；
- Dry Master 和必要的 Processed Variant；
- 每个声音的统一 Gain、Trim、Fade 和 Metadata；
- Pack Preview、Cover、Creator Credit；
- 完整原始工程、权利清单和交付说明。

具体 Pad 数量和角色应在发出正式 Brief 前与最新产品规格对齐，不能让供应商自行定义
新的 LMDJ 公开合同。

### 8.2 同时报三种授权价格

要求供应商分别报价：

1. **Non-exclusive OEM**：供应商仍可在其他地方销售，但 LMDJ 获得永久嵌入与分发权；
2. **Timed Exclusive**：LMDJ 获得一定期限或特定平台的独占权；
3. **Full Exclusive / Buyout**：供应商不再向其他客户提供同一内容，LMDJ 获得约定范围
   内的独占权或权利转让。

这样可以把“内容制作成本”和“独占性成本”分开比较。

### 8.3 供应商评估维度

| 维度 | 建议权重 |
| --- | ---: |
| 声音质量与风格匹配 | 25% |
| 权利来源与原创保证 | 20% |
| OEM / 再分发授权完整度 | 20% |
| Pad、Pattern 与元数据适配能力 | 15% |
| 修改轮次、响应和持续供货能力 | 10% |
| 总成本与独占性 | 10% |

任何存在未清权 Sample、第三方 Loop、设备 ROM、知名录音采样或来源不明素材的提案，
无论声音多好，都应直接触发 Hard Gate。

## 9. 合同必备条款

### 9.1 授权范围

合同应明确写入：

- 永久或明确足够长的期限；
- 全球范围；
- Web、PWA、Desktop、Mobile 和后续 LMDJ 平台；
- 内置、在线流式、离线缓存和下载；
- 免费、付费、订阅、Bundle 和促销；
- LMDJ 及其分发平台、CDN、应用商店和支付渠道；
- 允许 LMDJ 为运行时和产品体验进行修改。

### 9.2 终端用户权利

合同应明确允许 LMDJ 用户：

- 在 LMDJ 中演奏和编排声音；
- 录制、渲染和导出音乐；
- 商业发行其音乐作品；
- 在视频、直播、演出、游戏和其他作品中使用输出；
- 在约定范围内把输出交给合作音乐人、客户、发行商或平台。

### 9.3 原始资产导出

必须单独选择并写明：

- 允许导出原始 One-shot / Loop；或
- 只允许导出经过用户编排的 Stem / Loop / Mix；或
- 原始资产只能留在 LMDJ 运行环境中。

合同中的措辞要与实际 Creator Export 行为一致。

### 9.4 原创保证与赔偿

供应商应保证：

- 交付内容为原创或已经取得足够授权；
- 未使用未经披露的第三方 Sample Pack、Preset、Loop、歌曲或录音；
- 未采样受保护的硬件 ROM、游戏、影视或商业 Sound Library；
- 所有表演者、歌手、乐手和共同创作者均已签署授权；
- 有权授予 LMDJ 合同中的全部权利；
- 发生权利争议时承担约定责任并及时提供替换内容。

### 9.5 Content ID 与平台 Claim

供应商及 Creator 不得：

- 把 LMDJ Pack 的原始声音单独注册进 Content ID；
- 因用户合法使用该 Pack 而发起版权 Claim；
- 授权其他合作方以排他方式控制相同原始声音。

如果完成的 Demo 或歌曲需要进入 Content ID，必须排除对共享 Pack 素材本身的垄断性
Claim，并建立明确的争议处理窗口。

### 9.6 修改与衍生

LMDJ 应获得以下权限：

- Trim、Normalize、Fade、Loop；
- Resample、Pitch、Time-stretch；
- 转码、压缩、分块和加密；
- 制作 Preview、Demo 和营销素材；
- 转换 Metadata 和 Preset 格式；
- 为无障碍、性能、兼容性和后续平台制作衍生版本。

### 9.7 AI 权利单独处理

内容随软件分发的权利不应自动解释为模型训练权。合同应分别写明：

- 是否允许把声音用于分析、分类、相似度搜索和自动标签；
- 是否允许作为生成模型训练数据；
- 是否允许生成变体；
- 生成结果的权属；
- Creator 是否可以选择退出模型训练。

第一阶段可以只采购传统内容分发权，不必同时扩大到 AI 训练权。

## 10. 首轮询价模板

可向候选供应商发送以下英文 Brief：

```text
Subject: Custom Sound Set and OEM licensing inquiry for LMDJ

Hi,

We are developing LMDJ, a playable beat instrument that turns audio into
performance-ready material. We are exploring a small original factory Sound Set
for use inside the product.

We are looking for:
- original drum one-shots, bass/melodic material, phrases and textures;
- editable MIDI/pattern content and structured metadata;
- delivery in open WAV and data formats rather than third-party plugin presets;
- full provenance documentation for every source asset.

Please quote separately for:
1. non-exclusive OEM licensing;
2. time-limited or platform-limited exclusivity;
3. full exclusivity or buyout.

The required license should cover worldwide commercial embedding and
redistribution inside LMDJ, free or paid expansion delivery, runtime
modification/transcoding, offline caching, and end-user commercial music
creation.

Please also state whether end users may export isolated original samples, or
only rendered stems/loops/mixes created in LMDJ.

No uncleared third-party sample packs, commercial loops, copyrighted recordings,
hardware ROM samples or Content ID conflicts can be included.

Please share relevant factory-content work, estimated timeline, revision policy,
deliverables and pricing.
```

这个模板只是询价起点，不替代正式的技术 Brief、NDA 或合同。

## 11. 采购前必须回答的开放问题

1. LMDJ 第一阶段要的是内置 Factory Content，还是可单独购买的 Expansion？
2. Pack 素材能否通过 Creator Export 作为独立 WAV 导出？
3. 是否允许用户把 Pack 中的原始声音带到其他 DAW？
4. 首批目标风格是什么，谁负责 A&R 和声音验收？
5. 是否需要 Creator / Artist 联名，还是保持 LMDJ 自有品牌？
6. 是否要求独占；若要求，是全球、平台、品类还是时间窗口独占？
7. 是否会引入自有 Synth Engine；若没有，哪些“Preset”应降级为 Sample-based Sound？
8. Sound Set 的运行时 Manifest 是否属于新的内部合同，谁是唯一事实来源？
9. 免费 CC0 内容只用于原型，还是会进入正式发行？
10. 谁负责持续保存合同、来源、Hash、版本和下架记录？

## 12. 建议的下一步

### P0：先定义，不采购

1. 确认原始 Sample 导出边界；
2. 写一页 LMDJ Sound Set 技术交付规格；
3. 确认首批风格和声音验收负责人；
4. 准备统一 NDA、询价表和授权条款清单。

### P1：并行询价

向 New Loops、Mind Flux 和 Capsun ProAudio 发送同一份 Brief，并要求三种授权报价。
MSXII 可作为 Hip-hop / Beat 专项候选。

### P2：免费技术样本

可以用 VSCO 2 CE Raw WAV 制作一个不代表品牌声音的内部技术样本，验证：

- Sound Set Manifest；
- Multisample / Pad Mapping；
- 下载、缓存和版本；
- Provenance 与 License 展示；
- Creator Export 的授权边界。

### P3：签一单小型试验包

首单只验证一个主题和一套完整流程。通过声音验收、合同验收、运行时验收和真实
Creator Export 验收后，再决定是否建设长期内容商店。

## 13. 第一方来源

### 授权条款

- [Splice Terms of Use](https://splice.com/terms)
- [Loopmasters License Agreement](https://help.loopmasters.com/hc/en-us/articles/7718328554772-Loopmasters-License-Agreement)
- [Polyend Content Licensing Agreement](https://polyend.com/licenses/)
- [Freesound Licensing FAQ](https://freesound.org/help/faq/)
- [GeneralUser GS License](https://github.com/mrbumpy409/GeneralUser-GS/blob/main/documentation/LICENSE.txt)

### 免费素材

- [VSCO 2 Community Edition](https://versilian-studios.com/vsco-community/)

### 候选供应商

- [New Loops Professional Sound Design](https://newloops.com/pages/sound-design)
- [Mind Flux Sound Design Services](https://www.mind-flux.com/sound-design)
- [Capsun ProAudio](https://www.capsunproaudio.com/)
- [MSXII Sound Design](https://www.msxaudio.com/pages/about-msx)
