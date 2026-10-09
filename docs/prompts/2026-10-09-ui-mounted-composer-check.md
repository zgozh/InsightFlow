# 最终页面探针等待实际挂载

gpt-6-luna/max，所有权只frontend-release探针和2026-10-09-catalog-ui-deploy.md。主会话已独立读visibleTextarea：立即all枚举会在React挂载之前误报missing，后续toHaveValue等待无效。

最小修该helper：使用实际 `textarea:visible` first locator waitFor visible timeout10000，再返回locator，若timeout仅稳定missing错误码。不修改产品、不放宽prefill/edit/zeroPOST/sidebar/historicalchat断言、不构建部署。直接运行已有PS1一次，成功完整结果写短doc冻结；实际页面错误如再现给具体console/pageerror计数而非长正文。

当前前端365f5538…修复已部署，Gateway31e运行。旧e1f8镜像缺失不可写回滚passed；可在所有检查后只读确认仍保留fae原基底是否可rollback，不pull不prune。
