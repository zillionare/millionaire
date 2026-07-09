## 问题
`_git` 函数在 louke 0.7.5 和 0.8.0 都有 bug: 返回 `(returncode, None, None)` 而非 `(returncode, stdout, stderr)`.

```python
# louke/scout.py 0.8.0 第 ~313 行:
def _git(args, *cmd):
    return subprocess.run(['git', *cmd], cwd=Path.cwd(), capture_output=True, text=True).returncode, None, None
```

调用方期望 `(rc, out, err)` tuple:
```python
# louke/scout.py 0.8.0 `_ensure_release_branch`:
rc, out, err = _git(args, 'ls-remote', '--heads', 'origin', branch)
if rc == 0 and out.strip():  # AttributeError: 'NoneType' object has no attribute 'strip'
```

## 复现
1. 任意 louke 0.7.5/0.8.0 项目
2. 调用 `lk agent scout foundation` (触达 `_ensure_release_branch`)
3. 报 `AttributeError: 'NoneType' object has no attribute 'strip'`

## 期望
返回 `(returncode, stdout, stderr)` tuple, 让 `out.strip()` 正常:
```python
def _git(args, *cmd):
    result = subprocess.run(['git', *cmd], cwd=Path.cwd(), capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr
```

## 环境
- louke 0.7.5 / 0.8.0 (pip install louke)
- 触发项目: zillionare/millionaire (v0.2-003-coverage M-FOUND 阶段)
- reporter: aaron (via Maestro)
- 之前已开 issue: #93 #94 #95 (M-SPEC 阶段 3 个 Louke 0.7 兼容问题)
- 之前都 wont-fix 或已修 (#94 修)
- 本 issue (#1 真 bug) louke 应修

## 建议
- 短期 workaround: `pip install --force-reinstall louke==0.6.x` (旧版无此 bug)
- 长期: louke 0.8.x 修源码
