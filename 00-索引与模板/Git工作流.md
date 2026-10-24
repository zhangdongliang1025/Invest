# Git 工作流

> 本库的 git 使用规范。**不要在 `main` 上干活**，所有日常改动在 `V1` 上提交。
> 约定确立于 2026-10-24，远端仓库：`https://github.com/zhangdongliang1025/Invest`（**public**）。

## 一、分支模型

| 分支 | 角色 | 远端保护 | 怎么用 |
|---|---|---|---|
| `main` | 已发布基线 | 受保护：合入必须走 PR（通过审核数 0），**管理员可绕过**；禁止强推与删除 | 只作为对照基线，不直接改 |
| `V1` | **干活分支** | 无保护，可直推 | 任务直接在这里改、改完提交推送 |

本地默认停在 `V1`，`git status -sb` 应显示 `## V1...origin/V1`。

不切 `feat/xxx` 短分支——步骤更少是选这个拓扑的原因，**代价是单次任务无法独立回滚**：V1 上若积压了多个任务的改动，只能整体回退。需要单独回滚某次改动时，用 `git revert <sha>` 而不是 `reset`。

## 二、日常操作流程

```text
1. git status -sb              # 确认在 V1 上，工作区干净
2. …改文件…
3. git add -A && git status    # 核对暂存清单（见下方检查清单）
4. git commit -m "…"          # 只在 V1 上提交
5. git push origin V1          # 推送
6. gh api repos/zhangdongliang1025/Invest/commits/V1 --jq '.sha'   # 复核远端确实更新了
```

第 6 步不能省。`git push` 打印 `Everything up-to-date` **不等于**推成功——本地引用与远端不一致时它照样这么打印。看推送输出里有没有 `d7046be..a3acd88 main -> main` 这类真实更新摘要，再用 `gh api` 独立复核一次。

## 三、提交规范

- 一个任务一次提交，不把不相关的改动混进来。
- 提交信息写「为什么」，不写「改了什么」——改了什么看 diff 就知道。
- 改 `10-原始素材` 的正文算违规（铁律 1）：只允许改 frontmatter。
- 改了 `20-自研沉淀` 的结论，必须同步更新对应看板行与首页计数（铁律 3）。

## 四、推送前检查清单

仓库是 **public**，推上去的内容无法撤回。每次 push 前跑一遍：

```bash
git add -A && .backtest/prepush_check.sh
```

它一次跑完六项检查（体积 / 凭证 / 本机路径 / 链接一致性 / status 与标签一致性 / 素材正文零改动），
任一项不通过则退出码为 1。**既有问题登记为基线**，脚本只在超出基线时才判失败：

| 检查 | 基线 | 说明 |
|---|---|---|
| 链接一致性 | 3 处未解析 | 看板模板里的「素材名」占位符（双中括号形式）、`拥挤度指标.md` 及其备份里缺失的 `Pasted image 20261024131830.png` |
| status 与标签一致性 | 11 处问题 | 全在 `00-索引与模板/模板/` 的 4 个空模板里 |
| 素材正文零改动 | 0 | 跑 `.backtest/verify_raw_normalize.py`：拿整理前的原文（git 历史）逐字比对现在的正文、摘要、frontmatter，任何一个字的增删改都会报出来 |

基线数值写在 `.backtest/prepush_check.sh` 顶部的 `BASE_LINKS` / `BASE_STATUS`。
**修掉某个既有问题后记得同步下调基线**，否则基线会掩盖新问题。

> 第六项依赖基线提交 `778d307`（规范化之前的原文）。它通过 `BASE_COMMIT` 环境变量可覆盖；
> 基线之后**新增**的素材没有整理前原文可比，脚本会自动跳过并列出，不算失败。

## 五、仓库布局与忽略规则

`.gitignore` 排除：

| 排除项 | 原因 |
|---|---|
| `.backtest/data/` | 576M 行情数据，可由 `download_*.py` 重新获取 |
| `.backtest/venv/` | 101M 虚拟环境 |
| `__pycache__/`、`.DS_Store` | 构建与系统垃圾 |
| `.obsidian/workspace.json` | 本机 UI 状态，跨机器不通用 |

**入库的**：`10-原始素材`（含附件图）、`20-自研沉淀`、`99-归档`、`00-索引与模板`、`.backtest/` 下的脚本与 `out/` 结果、`.backup/`（归档索引的 sha256 校验依赖它）、`.obsidian/` 的 3 个配置文件。

写脚本时**不要写死绝对路径**，用相对定位：

```python
ROOT = Path(__file__).resolve().parent.parent
```

## 六、推送通道

本机到 `github.com:443` 经常超时或挂住，**SSH (22 端口) 正常**。仓库已配好重写，remote 存的仍是 HTTPS，实际走 SSH：

```bash
git config --local url."ssh://git@github.com/".insteadOf "https://github.com/"
```

推完想确认通道：推送输出的 `To ssh://git@github.com:...` 就是证据。

## 七、复核发布结果

推完别只看退出码，克隆一份独立复核：

```bash
git clone -q git@github.com:zhangdongliang1025/Invest.git .backtest/data/_clonecheck
cd .backtest/data/_clonecheck
python3 .backtest/validate_links.py
python3 .backtest/claim_scan2.py     # 应复现归档索引引用的 100% / 100% / 75%
rm -rf .backtest/data/_clonecheck
```

克隆到 `.backtest/data/` 下是因为它已被 `.gitignore` 忽略，不会污染工作区。

## 八、变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-24 | 建库并首次推送 `main`（`a3acd88`）；创建 `V1` 作为干活分支；`main` 开启分支保护（管理员可绕过） |
| 2026-10-24 | 发布前检查加到六项：新增「素材正文零改动」（`.backtest/verify_raw_normalize.py`，以 `778d307` 为基线逐字比对 `10-原始素材` 正文） |
