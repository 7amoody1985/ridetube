# RideTube · iDrive 7 简体中文

[English](README.md) · [简体中文](README.zh-CN.md)

RideTube 是 BMW iDrive 7（MGU）上的非官方 YouTube 客户端。登录后可在车机浏览首页、订阅和稍后观看，也可搜索视频和频道、选择章节、调节画质及跳过 SponsorBlock 标记的片段。声音通过车机媒体播放器输出。

翻译者：抖音「小白科技杂物社」 · BiliBili「小白151」 · GitHub [JackieZ123430](https://github.com/JackieZ123430)。

## 安装和首次使用

1. 在 MGU Store 添加 `JustAnotherPU/ridetube` 和 `JustAnotherPU/mgu-apps` 的 Releases 来源。
2. 连接车机 Internet Uplink，再从商店安装 RideTube。由商店解析播放器服务、渲染器和 Node.js 依赖。
3. 打开「首页」，用手机扫描车机二维码并输入屏幕上的登录码。授权保存在车机，应用不会读取手机输入的密码。
4. 从「搜索」「订阅」或「稍后观看」选择视频。默认停车时显示画面，行驶中切换为播客界面并继续播放声音。

以上是上游发行版的安装方式。简中源码构建命令见下方。

## 播放设置

- **填满屏幕**会裁剪画面，关闭时保留黑边。
- **视频画质**可选择自动、720p、480p 或 360p。自动模式在 Wi-Fi 下选 720p，在移动网络下选 480p。
- **SponsorBlock** 可按片段类型选择自动跳过、显示跳过按钮或关闭。
- **停车时暂停阈值**按 12 V 蓄电池电量设置。播放会消耗车机电力和流量。
- 登录、退出登录和搜索入口在应用菜单中。视频、频道和搜索词按原文显示。

## 构建简中界面

在项目根目录准备从自己车机提取的 `oap-sdk/`，再执行。Windows 下可以使用 `python`。

```sh
python3 kit/tools/build.py --language zh-CN jap_ridetube
```

简中包与上游同一应用 ID，使用上游的 RideTube 播放服务。主界面右上角和设置页保留汉化署名。中文字形使用 Noto Sans SC，标题备用图集覆盖 GB2312 汉字，生僻字和特殊符号的显示取决于字形覆盖。许可随字体资源保留。BMW SDK 和含有该 SDK 的构建包请留在本地。

## 来源

- [RideTube 原仓库](https://github.com/JustAnotherPU/ridetube)
- [简中 fork](https://github.com/JackieZ123430/ridetube-cn)
- [MGU Store](https://github.com/robertnisipeanu/mgu-store)

RideTube 是实验性社区应用，与 BMW、YouTube 和 Google 无关联。请在停车时配置和使用视频界面。上游的许可证和第三方声明见 [LICENSE](LICENSE) 与 [THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES)。
