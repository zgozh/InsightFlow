# Gateway locked 构建锁文件核对记录

## 结论

按主会话裁决，仅补齐已核实的 6 条同 hash 制品记录的 `size` 与 `upload-time` 后，完整结构与 HEAD 一致；随后已保存原镜像锁备份并恢复 HEAD canonical PyPI 锁字节。明确 PyPI、`--no-config`、`--locked --extra redis` 导入检查通过，锁 SHA 前后相同，`backend/uv.lock` 的 Git diff 为空。

## 首次归一比较（裁决前）

- 当前与 HEAD 均有 213 个包坐标；包名/版本坐标变化为 0，哈希变化为 0。
- 原始差异计数：registry 字段 210 项、制品 URL 2,120 项。
- 归一规则仅将 `https://pypi.tuna.tsinghua.edu.cn/simple` 映射为 `https://pypi.org/simple`，并将清华 `packages/` 制品 URL 主机前缀映射为 PyPI 文件主机前缀。比较过程只输出计数，不输出 URL。
- 归一后仍有 6 个制品记录缺少 HEAD 中的 `size` 与 `upload-time`：`defusedxml`、`jsonpatch`、`olefile` 各自的 sdist 和首个 wheel。合计 6 个记录、12 个缺失字段。除此之外，解析后的结构相同。
- 因此不满足“归一后完全一致”的恢复条件，未改写 `backend/uv.lock`。

## 首次 locked 检查（裁决前）

- HEAD `backend/uv.lock` SHA256：`46f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912`
- 当前及命令后 SHA256：`f0a475698b9e0173481087337ab18524716f5d3dc4308248db16059938593017`；命令前后相同。
- uv 版本：`uv 0.11.28 (ebf0f43d7 2026-07-07 x86_64-pc-windows-msvc)`。
- 唯一一次小型 locked import 检查，在 `backend/` 执行：

  ```powershell
  uv run --no-config --default-index https://pypi.org/simple --locked --extra redis python -c "import sqlglot, sqlalchemy, redis; assert sqlglot.__version__ == '30.18.0', sqlglot.__version__; print('imports-ok', sqlglot.__version__, sqlalchemy.__version__, redis.__version__)"
  ```

  退出码为 2，uv 在导入前报告 `uv.lock` needs to be updated；没有发生包导入，也没有网络错误。命令后锁文件 SHA256 未变。
- `git diff --check -- backend/uv.lock` 退出码为 0；记录文件已读回核对。

## 裁决后修复与最终验证

在内存中仅为上述 6 条记录补回 HEAD 的 `size` 与 `upload-time`，确认补齐后完整归一结构相等；包坐标和哈希均未变化。原始镜像锁已保存至忽略路径 `.reviews/lock-index-build-fix-20261008/backend-uv.lock.f0a475698b9e0173.before-canonical`，其 SHA256 为 `f0a475698b9e0173481087337ab18524716f5d3dc4308248db16059938593017`。随后 `backend/uv.lock` 恢复为 HEAD 字节，最终 SHA256 为 `46f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912`。

修复后唯一一次 locked import 检查在 `backend/` 执行：

```powershell
uv run --no-config --default-index https://pypi.org/simple --locked --extra redis python -c "import sqlglot, sqlalchemy, redis; assert sqlglot.__version__ == '30.18.0', sqlglot.__version__; print('imports-ok', sqlglot.__version__, sqlalchemy.__version__, redis.__version__)"
```

退出码为 0，输出 `imports-ok 30.18.0 2.0.49 7.4.0`。命令前后锁 SHA256 均为 `46f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912`，`git diff --check -- backend/uv.lock` 退出码为 0，`git diff --quiet -- backend/uv.lock` 退出码为 0（锁文件 Git diff 为空）。
