# 真实分析探针的 Windows 容器身份读取修正

gpt-6-luna/max。只拥有runtime-probes/run_analysis_runtime_probe.ps1的身份读取实现、必要的该目录私有辅助文件及原 preparation acceptance记录追加。CJS业务探针暂不改，startup/launcher/context/生产源码不动，与启动修复worker所有权独立。禁止ExecuteOnce/API mutation/seed/model；只准备+验证元数据读取。

Principal审查确认当前inspectFormat含Go `index .Config.Labels "com.docker.compose.service"`和`printf "..."`。Windows PowerShell native argv会剥这些内部双引号；同环境已实际多次复现template parsing error: function com not defined。先修好，防止启动就绪后又在首个guard阻断。

用无内部引号的简单字段或JSON片段：Name、Image、State.Status、json Config.Labels、json NetworkSettings.Ports。在内存解析labels/ports，仅读project/service/name/image/status/HostIp/HostPort，不读Env、不输出完整labels或inspect。保留严格fixed project、exact4服务、所有running、期望Gateway/FrontendID、仅Nginx127.0.0.1:29388、其余无published ports、禁止29384/29385的既有guard。预期非零native命令用局部EAP=Continue捕获真实exit并形成稳定code，不任由PowerShell包装错误输出原生正文。

若已有helper可私有复用则用它，不搭新框架、不增加公共CLI/test mode。语法AST/node证据保持；只需要一轮实际只读Docker元数据解析check（新project已partial4服务，Gatewayexited1/Nginxcreated，这是当前已知事实；读取可成功，运行状态guard应拒绝，不执行credentials/API/CJS）。不要因partial状态启动容器。记录safe counts/布尔/稳定拒绝code，绝不ExecuteOnce触发真实分析。冻结diff与exact检查结果。
