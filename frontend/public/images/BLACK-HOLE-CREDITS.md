# 黑洞视觉资源

## 真实照片 favicon

- 原图：ESO [First Image of a Black Hole / eso1907a](https://www.eso.org/public/images/eso1907a/)。照片内容是 2019 年发布的 EHT M87\* 图像。
- 图片署名：**EHT Collaboration**。
- 下载地址：https://cdn.eso.org/images/screen/eso1907a.jpg 。本地保留 `eht-m87-source.jpg`，1280 × 746。
- 许可：ESO [使用政策](https://www.eso.org/public/outreach/copyright/)正文标明一般图片适用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，允许适配且要求清晰可见署名。图片页未标明更严格例外；不能据此暗示 EHT 或 ESO 为本项目背书。
- 适配：裁切原图 `(410, 145, 870, 605)` 区域，以 Lanczos 缩放至 32 × 32，生成 `public/favicon.png`；同一裁切生成 `public/favicon.ico` 的 16/32 像素版本。首页页脚显示署名、适配说明、原图及许可证链接。

## 原创动态背景

`black-hole-scene.svg` 由 `frontend/scripts/generate-black-hole-assets.py` 以固定随机种子生成：细颗粒吸积盘、背侧透镜弧、暗核心、星场与外围尘埃。组件 `black-hole.tsx` 用同一坐标系绘制动态颗粒。两者均为本项目原创代码，按仓库 MIT 许可分发。

构图参考 [NASA 科学可视化](https://svs.gsfc.nasa.gov/14619/)和 [ebruneton/black_hole_shader](https://github.com/ebruneton/black_hole_shader)的视觉关系，没有复制其代码、图片或视频。这是艺术模拟，不是物理精确光线追踪。底景作为外部 SVG 图片加载，不将颗粒节点注入 HTML DOM；未新增运行依赖。
