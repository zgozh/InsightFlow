# 已确认的 Windows PowerShell 文件编码修复

gpt-6-luna/max。只改runtime-probes/run_analysis_runtime_probe.ps1的编码和准备记录，不再改业务逻辑/native transport/集合/CJS。

Principal现已确认根因：宿主Windows PowerShell major=5，Default.CodePage=936，runner没有UTF-8 BOM。相同文件UTF8解码ParseInput时records初始化AST=1；按936解码时records初始化AST=0，两者parse errors均0。中文注释的错误解码吞掉紧接的初始化语句，解释了先前Format为空、records加法与List为空系列症状。这不是新的框架问题。

原文件用明确UTF8读取，按UTF8 BOM写回，保持正文完全一致（例如Python读encoding=utf-8再写encoding=utf-8-sig，或.NET UTF8Encoding(true)）。不要重新汉化注释或修改语句。验证bytes前3位EF BB BF、去BOM正文hash与before一致，再正式无ExecuteOnce调用固定c7fe6b3b50e02b99c427ac0240687c48db82475e698c0617e36c2c964ad39e63与fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c。

预期身份accepted=true，然后explicit_execute_once_required退出。无凭据/API/seed/model/container修改。记录exact检查结果与此次编码根因，马上冻结供Principal review，不扩大其它PS文件转换（startup证据已经通过，保留）。
