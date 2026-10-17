# 素材授权 / Asset License

## 适用范围

本文件适用于 Claude-Chan 的角色素材：

- `resources/assets/`、`resources/assets-chibi/` 下的关键帧图片、动画（AVIF / WebM）和 `hitmask.png`；
- `resources/icon.png`；
- 发布包（Release）里随附的同一套素材。

源代码和文档使用 MIT 许可证，见 [LICENSE](LICENSE)。`manifest.json` 是数据描述文件，也按 MIT 处理。

## 人设出处

Claude-Chan 的角色设计来自 B 站 UP 主 **ZipZipPipe** 的动态[《所有的AI们，和OpenCode》](https://www.bilibili.com/opus/1233069202138464289)（2026 年 8 月）。本项目的立绘、各状态的关键帧和动画都是在这份人设的基础上用 AI 二次创作的。**角色设计本身的权利归原作者 ZipZipPipe 所有。**

## 许可

这些素材以 **[知识共享 署名 4.0 国际许可协议（CC BY 4.0）](https://creativecommons.org/licenses/by/4.0/deed.zh-hans)** 授权。

你可以自由地复制、分发、修改和用于任何目的（包括商业用途），只需要：

- **署名**：注明素材来自 Claude-Chan（附上项目地址），并注明使用的许可协议；
- **说明改动**：如果修改了素材，注明做了修改。

建议的署名写法：

> 角色素材来自 [Claude-Chan](https://github.com/Ivanfangsc/claude-chan)，CC BY 4.0。

## 不在授权范围内的东西

CC BY 4.0 只涉及本项目作者对这些素材享有的权利，**不授予以下任何权利**：

- **角色设计**：人设属于原作者 ZipZipPipe（见上）。本许可只覆盖本项目自己做的部分（姿势、动画、Q 版造型等），不包括原人设本身；超出本项目展示和二次创作的用途，尤其是商业用途，请先取得原作者的许可。

- **商标与品牌**："Claude" 是 Anthropic, PBC 的商标。Claude-Chan 是**非官方的同人作品**，与 Anthropic 没有任何关联，也未经其认可或赞助。使用这些素材时，不得暗示与 Anthropic 有关联，也不得用其名称或品牌宣传你的产品；涉及商标的用途请自行取得权利人的许可。
- **第三方权利**：如果你的用途还涉及其他人的权利（例如肖像、其他作品），需要自行处理。

## 素材由 AI 生成

全部素材都由 AI 模型在本机生成，再经过人工挑选、对齐和后期处理：

- 关键帧：用 **Qwen Image 2.1** 从一张立绘编辑出各个状态和 Q 版形象；
- 动画：用 **MiniMax H3**（图生视频）生成，再抠图、拼接成循环。

制作方法见 [docs/animation-pipeline.md](docs/animation-pipeline.md)。

这两个模型各有自己的许可证，约束的是**使用模型的人**。如果你想用同样的方法生成新素材，请先阅读并遵守它们的条款，尤其是 [MiniMax H3 社区许可协议](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) 对适用地区的限制，以及 Qwen Image 2.1 研究许可证对商业用途的限制。

---

## English summary

The character design is by Bilibili creator **ZipZipPipe** ([post](https://www.bilibili.com/opus/1233069202138464289), August 2026); all rights in the original design remain with them. The CC BY 4.0 license below covers only this project's own contributions (poses, animation, the chibi version, etc.), not the original design; for other uses of the character, especially commercial ones, obtain the original author's permission.

The character art, keyframes and animations in `resources/` (and the same assets in release packages) are licensed under **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**: you may share and adapt them for any purpose, including commercially, as long as you give appropriate credit ("Character assets from Claude-Chan, CC BY 4.0", with a link) and indicate if changes were made. The source code is MIT-licensed (see `LICENSE`).

"Claude" is a trademark of Anthropic, PBC. Claude-Chan is an **unofficial fan project**, not affiliated with, endorsed or sponsored by Anthropic. This license grants no trademark rights; do not imply any affiliation with Anthropic.

All assets were generated with AI models (Qwen Image 2.1 for keyframes, MiniMax H3 for animation) and then curated and post-processed by hand. Those models have their own licenses that govern anyone who uses them to generate new assets.
