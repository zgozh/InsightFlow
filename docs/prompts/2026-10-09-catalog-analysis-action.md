# 目录到分析的实际操作衔接

gpt-6-luna/max。读frontend AGENTS。用户强调二开功能可从前端操作，复用成熟设计不增加架构。

独立所有权：前端数据源/指标目录页面组件、既有新建分析输入预填相关组件及直接相关tests，frontend/AGENTS.md如需说明该新交互，以及 docs/acceptance/2026-10-09-catalog-analysis-action.md。不可修改后端、README、其它验收/部署/PROGRESS/INTERRUPTION，与安全APIworker隔离；**不构建/部署，不发模型**。

实现最小可操作衔接：用户可见的数据源卡片/指标条目提供“使用此数据源分析”/“分析此指标”操作，进入已有 `/workspace/analysis/new` 并将资源名称/key转成可编辑自然语言问题预填，绝不自动发送。优先复用现有欢迎示例/输入预填机制；不要发明服务端context授权键、picker框架或后端接口。需要query参数时仅在新建分析读取，合理长度上限；历史thread/普通聊天不受影响。信息来自已授权目录，前端传入名字只是用户目标，服务端inspect_business_catalog与policy仍最终授权，不将前端选择等同获得权限。

没有可用资源的现有空态保留；管理员/普通用户都能对自己可见条目执行操作，普通用户仍无管理员控件；不新增虚假数据或多余提示弹窗。样式沿用现有按钮/link与i18n中文/英文。

用最小相关组件测试验证点击去分析、预填可编辑且零自动提交、普通聊天/历史分析不被query覆盖。适用typecheck与受影响文件lint/format一次，不重复全frontend suite/build。短记录实际diff/checks后立即冻结供Principal独立审查，再安排一次最终前端构建部署。若现有组件机制已完全支持，只补最少连接。
