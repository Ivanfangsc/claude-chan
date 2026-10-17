# 素材授权 / Asset License

## 适用范围

本文件适用于 Claude-Chan 的角色素材：

- `resources/assets/`、`resources/assets-chibi/` 下的关键帧图片、动画（AVIF / WebM）和 `hitmask.png`；
- `resources/icon.png`、`docs/images/` 下的图片；
- 发布包（Release）里随附的同一套素材。

源代码和文档使用 MIT 许可证，见 [LICENSE](LICENSE)。`manifest.json` 是数据描述文件，也按 MIT 处理。

## 人设出处

Claude-Chan 的角色设计来自 B 站 UP 主 **ZipZipPipe** 的动态[《所有的AI们，和OpenCode》](https://www.bilibili.com/opus/1233069202138464289)（2026 年 8 月），原作者声明这些形象**依 CC BY-NC-SA 4.0 非商业使用，二创同协议授权**。

本项目的立绘、各状态的关键帧、Q 版形象和动画，都是在这份人设基础上用 AI 二次创作的，因此按原作者的要求，以同样的协议发布。

## 许可

这些素材以 **[知识共享 署名-非商业性使用-相同方式共享 4.0 国际许可协议（CC BY-NC-SA 4.0）](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans)** 授权。

你可以复制、分发、修改这些素材，条件是：

- **署名**：同时注明原人设作者 ZipZipPipe 和本项目，附上链接和许可协议；如果修改了素材，注明做了修改；
- **非商业性使用**：不得用于商业目的；
- **相同方式共享**：基于这些素材再创作的作品，也必须以 CC BY-NC-SA 4.0 发布。

建议的署名写法：

> 角色素材来自 [Claude-Chan](https://github.com/Ivanfangsc/claude-chan)，人设原作 [ZipZipPipe](https://www.bilibili.com/opus/1233069202138464289)，CC BY-NC-SA 4.0。

需要商业使用的，请先取得原人设作者 ZipZipPipe 的许可。

## 不在授权范围内的东西

- **商标与品牌**："Claude" 是 Anthropic, PBC 的商标。Claude-Chan 是**非官方的同人作品**，与 Anthropic 没有任何关联，也未经其认可或赞助。使用这些素材时，不得暗示与 Anthropic 有关联；本许可不授予任何商标权利。
- **第三方权利**：如果你的用途还涉及其他人的权利（例如肖像、其他作品），需要自行处理。

## 素材由 AI 生成

全部素材都由 AI 模型在本机生成，再经过人工挑选、对齐和后期处理：

- 关键帧：用 **Qwen Image 2.1** 从一张立绘编辑出各个状态和 Q 版形象；
- 动画：用 **MiniMax H3**（图生视频）生成，再抠图、拼接成循环。

制作方法见 [docs/animation-pipeline.md](docs/animation-pipeline.md)。

这两个模型各有自己的许可证，约束的是**使用模型的人**。如果你想用同样的方法生成新素材，请先阅读并遵守它们的条款，尤其是 [MiniMax H3 社区许可协议](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) 对适用地区的限制，以及 Qwen Image 2.1 研究许可证对商业用途的限制。

---

## English summary

The character design is by Bilibili creator **ZipZipPipe** ([post](https://www.bilibili.com/opus/1233069202138464289), August 2026), who licenses it under CC BY-NC-SA 4.0 and requires derivative works to use the same license. The character art, keyframes, chibi version and animations in this project (in `resources/`, `docs/images/`, and the same assets in release packages) are derivative works and are therefore licensed under **[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)**: you may share and adapt them for non-commercial purposes, crediting both ZipZipPipe and this project, and you must license your adaptations under the same terms. For commercial use, obtain permission from the original character designer. The source code is MIT-licensed (see `LICENSE`).

"Claude" is a trademark of Anthropic, PBC. Claude-Chan is an **unofficial fan project**, not affiliated with, endorsed or sponsored by Anthropic. This license grants no trademark rights.

All assets were generated with AI models (Qwen Image 2.1 for keyframes, MiniMax H3 for animation) and then curated and post-processed by hand. Those models have their own licenses that govern anyone who uses them to generate new assets.
