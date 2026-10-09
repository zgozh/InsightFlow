# 无历史上下文的一次性调度正例

gpt-6-luna/max。主会话独立审查：已验证的正常分析成功；旧scheduler在反复使用带多个成功/失败工具历史的同一thread后，Reviewer以evidence_mismatch拒绝。现有reviewer收到真实snapshot，尚无证据证明其拒绝是错误；不为了过验收修改Reviewer或绕过它。

只变更测试的上下文前提：B通过现有API创建一个新的kind=analysis thread（即用户新建分析），任务reuse_thread指向这个**无历史**线程；问题使用已成功正例的逐月收入/合计/两位小数/未知unit说明，不额外带“重做旧报告”等旧scope目标。禁止fresh_thread_per_run默认chat被当成analysis。

所有权final-integration-current自己的fresh-scheduled独立context/claim/evidence/helper与final-scheduler-recovery记录。只一次自动once，90秒合法delay，新task/claim，不复用失败task，不删除旧claim。创建马上saveID，只有一次effective model run；结束确保task终态/停用。

成功证据：新analysis ownerthread，无旧run/evidence历史，noninteractive context受server控制，工具schema仅三个受控工具且无askclarification，SQL→Data→Writer→Reviewer→Publish成功stage；publishedreport归属newrun，3个月值和3901.25、unit未知、证据属于newscope，artifact API下载可读。不要重跑browser/report旧正例/安全/PGrestart。

失败即冻结：具体闭合stage/reason，无重发，无新生产patch。成功也要如实保留reuse有历史thread的Reviewer拒绝样例作为失败处理证据，不能删掉或宣称任意历史组合均成功。
