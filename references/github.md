# GitHub 发布操作手册

脚本运行在 macOS 或 Linux，需要 Git、Python 3.8+ 和支持 `gh auth token --user`、`gh auth status --json hosts`、`gh api --slurp` 的 [GitHub CLI](https://cli.github.com/)。macOS 可用 `brew install gh` 安装。下文 `"$publisher"` 指本 skill 目录下 `scripts/github_publish.py` 的绝对路径。用户输入用单独参数传递。

## 登录和预览

```sh
python3 "$publisher" accounts
python3 "$publisher" owners --account "$account"
python3 "$publisher" inspect --root "$project_root" --target "$target" \
  --account "$account" --protocol "$protocol"
```

- 缺账号时在用户终端用 `gh auth login --hostname github.com --web --skip-ssh-key` 登录。添加多个账号时分别登录，再重跑 `accounts`。脚本在本地读取所选账号的凭据并调用 `/user` 核验，不打印令牌或切换活跃账号。组织列表可能受 token 权限和 SSO 限制。
- `--root` 默认当前目录。`--target` 接受 `owner/repo`、`https://github.com/owner/repo` 和 `git@github.com:owner/repo.git`。也可用 `--owner` 和 `--repo`。协议默认 HTTPS。选择 SSH 时可加 `--ssh-host "$alias"`，使用绑定到 github.com 的现有本机别名。首次连接请核验 [GitHub 官方 SSH 主机指纹](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)。
- `inspect` 可用于没有初始化 Git 的目录，返回本地路径、Git 根目录、当前分支和 HEAD，以及远端仓库 ID、可见性、权限和 refs。目的地会显示 `empty`、`nonempty` 或 `missing_or_hidden`。后者无法区分未创建和权限隐藏。目标非空时结束首次发布流程。

## 发布与验证

先向用户展示完整发布方案，等用户确认目标归属、仓库名和发布动作。用户也可以亲自运行下面的命令。用 `--confirm-target` 传入确认的 `owner/repo`，脚本会将其与 `--target` 解析出的仓库比较。

```sh
python3 "$publisher" publish --mode create --root "$project_root" \
  --target "$target" --confirm-target "$confirmed_owner_repo" \
  --account "$account" --visibility "$visibility" \
  --protocol "$protocol" --branch "$branch" --head "$sha" \
  --description="$selected_description" --topic "$selected_topic"
```

- 将预览里获选的 Description 传给 `--description`，每个获选的 Topic 各传一个 `--topic`。Website 获选时才加 `--homepage="$selected_website"`。留空或跳过的字段省略参数。
- 复用空仓库时改用 `--mode existing --repo-id "$reviewed_repo_id"`，传入已核对的真实可见性。已有不同的简介或主页时在预览里保留现值，省略相应参数。Topics 在保留已有标签的基础上添加。
- 脚本复核 Git 根目录、当前分支、完整提交 SHA、Git URL、远端身份、可见性和空仓库状态。新仓库关闭远端初始化。推送只创建目标分支，Git 会拒绝覆盖途中出现的不同提交。已有标签和其他本地分支留在本地。先确认 LFS 端点和上传范围，再处理含 LFS 的项目。脚本验证 Git refs，LFS 对象需要另行核对。把 push 触发的工作流影响纳入预览。
- 完成后输出仓库链接、分支、已回读的提交和资料状态。Git 推送用临时 remote。若预览包含本地关联，推送后可复用唯一 fetch/push URL 都吻合的 remote，或用未占用的 `origin`、`github` 等名称新增。保留不同的 upstream，除非用户要求切换。普通 Git 操作继续由本机凭据配置决定。

## 中断恢复

```sh
python3 "$publisher" resume --root "$project_root" --target "$target" \
  --confirm-target "$confirmed_owner_repo"
```

`publish` 将计划和 `operations.repository`、`operations.push`、`operations.metadata` 保存到 Git 目录下的 `github-repo-publish`。状态 `requested` 代表已发出或即将发出请求，结果待回读，`verified` 代表已验证，`skipped` 代表计划里没有资料变更。记录不含登录凭据。

- **建仓已确认。** 用 `inspect` 核对仓库 ID 和可见性，再 `resume`。远端仍为空时重试同一个提交。远端分支已经处于计划中的 SHA 时直接验证并进入资料阶段。
- **建仓请求没有收到响应。** 先 `inspect`。同名仓库仍不可见时，`resume` 可重试创建。出现同名仓库时核对 ID、归属、可见性和是否为空，得到用户明确同意后使用 `resume --repo-id "$reviewed_repo_id"`。遇到不同仓库 ID、可见性变化或未核对的远端提交，停在检查。
- **代码已验证，资料未完成。** `resume` 回读分支和仓库资料，仅补仍缺的字段和 Topics。出现冲突时报告实际值。如果完整发布已经验证，再次 `resume` 只核对结果。

## 三次真实发布的记录方法

用日常的 CLI 或 Desktop 流程作为基线。从开始准备项目到拿到验证结果，记录手工步骤数、耗时、账号与归属是否正确、提交是否正确，以及中途返工。可以在同一聊天用下表记录。

| 场景 | 常规流程步骤 / 耗时 | Skill 步骤 / 耗时 | 目标与 SHA 核对 | 返工 |
| --- | --- | --- | --- | --- |
| 没有本地提交 | | | | |
| 已有本地提交 | | | | |
| 工作账号发布到组织 | | | | |

至少两次减少手工操作，且目标和提交都无需返工，再继续完善。按实际重复操作决定是否添加本地预设、自动截图或其他平台。
