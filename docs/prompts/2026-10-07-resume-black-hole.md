# 2026-10-07 续接：黑洞首页实施切片

执行者：按用户恢复后的最新指令使用 `gpt-6.1-sol`，`reasoning_effort=medium`。先读取根、frontend 和 frontend/src 的 AGENTS.md，以及 `docs/prompts/phase-06f3f21-immersive-black-hole-landing.md`。本文件是主会话恢复后的补充裁决，主会话负责方案与独立审查。

## 当前授权与范围

用户已要求恢复二开任务，并明确要高级颗粒感、赛博感的黑洞粒子背景，参考开源视觉和 DeerFlow 原粒子鹿。恢复起点为 `a678d54`，两个未跟踪的 6F3F20/21 提示词是保存的工作，不覆盖或删除。先完成 6F3F21，再由主会话审查并安排后端剩余闭环。不要自行展开新 Agent 角色架构、RAG 或全量验收。

实现文件归你独占：首页 Hero/新的黑洞组件、favicon/必要署名与 i18n、直接相关 landing 测试、6F3F21 acceptance 和 PROGRESS 更新。本提示词只由主会话编写。不得修改 6F3F20 提示词。

## 视觉裁决

首屏铺满深空背景，主体是倾斜的暖金/红橙颗粒吸积盘、暗事件视界、背侧透镜光弧；微星场、细粒尘埃和流入轨迹提供深度。避免粗矩形像素和孤立右侧框。文字保留现有中文，左侧阅读区通过局部暗遮罩保持可读；手机同一构图自适应。实现为自有 Canvas/WebGL/SVG 代码，优先利用现有能力，无新增渲染依赖。不要用 AI 栅格图片替代动态图形。

已查看的参考：
- https://github.com/ebruneton/black_hole_shader （WebGL2 黑洞吸积盘和星场，BSD-3-Clause；仅参考视觉，未授权照搬代码）
- https://svs.gsfc.nasa.gov/14619/ （吸积盘透镜弧的科学视觉参考）
- https://www.eso.org/public/images/eso1907a/ （真实 M87* favicon 来源，credit: EHT Collaboration）
- https://www.eso.org/public/outreach/copyright/ （核对 CC BY 4.0 与署名条件）

ui-ux-pro-max 已读；设计检索在 Windows 默认 GBK 下输出失败，主会话以 `python -X utf8` 重跑。用户指定暖橙黑洞优先于通用 SaaS 配色建议。无障碍、触控、响应式、减动效规则适用。

## 验证与交付

V2：受影响静态/格式检查、typecheck、landing 定点浏览器测试及完整桌面/手机截图；检查减动效、无 Canvas 静态退化、CTA/外链、favicon 获取解码。只在源码视觉与检查成功后按原 6F3F21 约束更新固定栈 Frontend。若 Docker 不可用，先记录真实原因，仍完成可行的源码与本地浏览器验证，不谎称已部署，不做全栈重建。

主会话在你实施时不做并行仓库工作。请每约 60 秒发简短进度，最后给实际 diff/文件列表、准确命令与结果、两种尺寸截图绝对路径、服务变更与尚缺证据，等待独立目视审查。提交先不做，待审查后由下一指令处理，避免把未审查视觉当成通过。不要 push，不打印凭据或业务正文，不发模型请求。
