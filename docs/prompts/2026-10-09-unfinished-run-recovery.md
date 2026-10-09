# 未完成运行恢复最后门禁

gpt-6-luna/max，独占 `.reviews/final-postgres-runtime-20261008/unfinished-recovery/` 与 docs/acceptance/2026-10-09-unfinished-run-recovery.md。不改生产/配置、不付费模型、不重启既有应用/PG、不碰scheduler线程和其他worker文件。

正常成功历史/PGcheckpoint复用/取消/timeout均已有证据不重跑；最后缺的是未完成run恢复不得伪装success。先有界读runtime真实RunManager/startup recovery入口与对应既有tests，优先复用已有FakeAgent/阻塞graph注入seam，在独立进程连接当前真实PG持久化，创建独立合成thread/run并用真实worker把其推进running，暂停于无副作用async阻塞点，杀该**自己启动的**helper进程模拟中断；下一独立helper进程运行生产恢复逻辑，核对该owner/thread run真实terminal interrupted/error和结构化事件，不伪造success、不修改旧数据、不清全表。

不允许直接手写running/success状态来冒充真实worker运行；可用现有公开service方法/本地fixture注入点，不发明新的production接口或通用恢复框架。实际app当前其它run都terminal但仍须按精确合成scope选择，不能恢复/取消别人的运行。必要测试DB可在已有PG上新独立schema/database以避免prodRunManager全局reconcile，但默认不创建新容器，synthetic credentials only memory。若需要专用DB/跨process权限先给准确内部方案由Principal判定，不机械等待用户批准。

如现有生产恢复API没有精确scope，只能全局扫，则不能在当前真实app库执行，改用独立合成PG database并同production库schema迁移，保留数据/清理自己的资源，记录实际范围。不可为了满足live创建庞大脚本或装依赖；现有test工具可复用。

先给可执行最短路径与实际code定位，再执行有界一次，稳定status/event/count/hash，不打印SQL/credentials/provider/messages。无法直接构建时明确缺哪一条机制，不说passed。短记录冻结供最终review，其他功能和正例全不重跑。
