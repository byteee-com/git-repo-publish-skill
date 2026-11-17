# Codeup 配置与首次发布

当前支持云效 **中心版**（`codeup.aliyun.com`）的 HTTPS 发布。需要 macOS 或 Linux、Git 和 Python 3.8+；不依赖 `gh` 或阿里云 AccessKey。Region 版、自定义域名及 SSH 发布暂未实现。SSH 地址可作为目标输入，但实际推送仍使用 HTTPS，必须在预览中说明。

## 配置组织和账号

1. 在组织管理后台的基本信息页获取组织 ID。在 Codeup 复制目标组织或代码组的完整路径，例如 `org-path`、`org-path/team` 或 `org-path/team/subteam`。组织 ID 与 URL 中的组织路径是不同字段，不要相互替代。
2. 在个人设置的 HTTPS 密码页查看 **克隆账号**，不要使用令牌名称代替账号。
3. 在个人设置创建个人访问令牌。发布需要「代码管理 / 代码仓库」读写、「代码组」只读（核对父路径）以及「分支」只读（回读 SHA），并需要账号本身拥有目标代码组的建仓或目标仓库的推送权限。令牌不能增加账号本来没有的权限。
4. 在用户终端中通过密码管理器或隐藏输入设置 `CODEUP_TOKEN`。不要让用户把令牌粘贴到聊天，不要将其写入项目文件、URL 或命令参数。Agent 无法继承终端环境时，请用户在同一终端自行执行检查和发布命令，或按客户端方式提供环境变量；不要为读取令牌输出环境。

隐藏输入示例（zsh）：

```sh
read -rs 'CODEUP_TOKEN?Codeup token: '
export CODEUP_TOKEN
```

以下 `"$publisher"` 为本 skill 的 `scripts/codeup_publish.py` 绝对路径。配置命令仅写本地非敏感配置，不调用 API，也不建仓或推送：

```sh
python3 "$publisher" configure --profile work \
  --organization-id "$organization_id" \
  --namespace "$full_parent_path" --username "$clone_username"
python3 "$publisher" config --profile work
```

默认配置文件为 `${XDG_CONFIG_HOME:-$HOME/.config}/git-repo-publish/codeup.json`。所有命令可用 `--config /absolute/path/codeup.json` 指定位置。配置内容只包含组织 ID、父路径、克隆账号和令牌环境变量名称。使用不同 `--profile` 保存多个组织或账号；`--token-env CODEUP_WORK_TOKEN` 可为不同账号指定不同变量。`config` 只返回令牌是否已设置，不显示令牌或验证远端身份。`configure` 会替换同名配置档，应在已确认这些配置字段后执行；不会修改全局 Git 凭据、已有 remote 或 upstream。

## 检查并预览

```sh
python3 "$publisher" inspect --profile work --root "$project_root" \
  --target "$full_target_path"
```

目标支持完整 `组织路径/代码组/仓库`、Codeup HTTPS 网页/克隆 URL、SSH 克隆地址，或当前配置父路径下的单个仓库名。脚本核对目标父路径必须与配置档完全一致；嵌套代码组不要压缩成 GitHub 风格的 `owner/repo`。调用 API 前将完整仓库路径编码成单个 URL 路径参数。

`inspect` 为只读操作，返回配置档、命名空间 ID、本地 Git 根目录、分支、HEAD、仓库详情和所有远端 refs。目的地为 `empty`、`nonempty` 或 `missing_or_hidden`；404 不代表可以区分不存在与无权查看。API 与 Git 认证都使用指定环境变量中的令牌；克隆账号是用户配置值，不能宣称已通过 GitHub 式用户接口核验。认证失败时核对账号和令牌是否属于同一用户。

按 [SKILL.md](../SKILL.md) 检查拟发布内容，展示完整预览并等待用户明确确认。预览必须包含平台、配置档、组织 ID、完整目标路径、命名空间 ID、克隆账号、项目路径、拟发布范围、分支、完整 SHA、新建/复用、可见性、HTTPS 协议和资料候选。默认 `private`；`internal` 是组织内公开，并非互联网公开。Description 对应简介，Topics 对应 Codeup 标签；不对标签套用 GitHub 的小写限制。Website 无对应写入字段，留在 README 或跳过，不传 `--homepage`。

## 创建或复用空仓库

用户确认完整方案之后，才将其确认的完整目标传入 `--confirm-target`：

```sh
python3 "$publisher" publish --profile work --root "$project_root" \
  --target "$full_target_path" --confirm-target "$confirmed_full_target_path" \
  --mode create --visibility private --branch "$branch" --head "$full_sha" \
  --description="$selected_description" --tag "$selected_tag"
```

每个标签传一个 `--tag`；跳过的资料省略参数。用户明确指定已有空仓库时，改为 `--mode existing --repo-id "$reviewed_repository_id"`，并采用检查出的实际可见性。只有没有任何 refs 的目标可以首次发布。脚本使用 `readMeType: EMPTY` 关闭远端 README 初始化，不创建父代码组；父路径必须已存在且由 API 回读核对。

脚本核对本地分支和 SHA，只创建目标分支，不覆盖已出现的分支；保留本地 remote 和 upstream。推送后同时通过 Git refs 和 Codeup 分支 API 核对 SHA，再补简介和标签。已有不同简介时停止，标签在保留现有标签的基础上添加；没有元数据冲突时再继续。Git LFS 对象和推送会触发的流水线按 GitHub 手册中的通用项目检查方法另行核对，Git refs 验证不代表 LFS 内容验证。

## 中断恢复

```sh
python3 "$publisher" resume --profile work --root "$project_root" \
  --target "$full_target_path" --confirm-target "$confirmed_full_target_path"
```

恢复记录写在 Git 公共目录的 `codeup-repo-publish`，与 GitHub 记录隔离，以组织 ID 和完整目标路径区分。不保存令牌。恢复核对原项目根目录、配置档字段、父路径 ID、仓库 ID、可见性和本地分支/SHA；配置档变化时先恢复原设置或重新核对方案，不跨目标恢复。

- 创建请求中断后先运行 `inspect`。若出现同名空仓库，向用户展示 ID 并获得明确同意，再用 `resume --repo-id "$reviewed_repository_id"` 选用。已核验仓库 ID 后无需再次传该参数。
- 推送结果未知时，只有远端唯一 refs 已指向计划 SHA 才可作为本次已完成的推送。不同 SHA 或其他 refs 会停止恢复。
- 代码已推送、资料或 API 核验未完成时，保留记录并重跑 `resume`。完整成功后再次 `resume` 仅回读验证，不重复建仓或推送。

配置和自动测试不等于真实发布验证。没有用户账号与明确发布授权时，不创建试用仓库。报告实际验证范围，并按 GitHub 手册的试用表记录后续真实使用结果。

## 官方依据

- [服务接入点](https://help.aliyun.com/zh/yunxiao/developer-reference/service-access-point-domain)与[个人访问令牌](https://help.aliyun.com/zh/yunxiao/developer-reference/obtain-personal-access-token)
- [个人认证设置与克隆账号](https://help.aliyun.com/zh/yunxiao/user-guide/personal-authentication-settings/)
- [查询代码组空间](https://help.aliyun.com/zh/yunxiao/developer-reference/getnamespace-query-code-group-space-information)
- [创建代码库](https://help.aliyun.com/zh/yunxiao/developer-reference/createreposition-creates-a-code-base)、[查询代码库](https://help.aliyun.com/zh/yunxiao/developer-reference/getrepository-query-the-code-base)、[更新代码库](https://help.aliyun.com/zh/yunxiao/developer-reference/updatereposition-update-the-code-base)
- [查询分支信息](https://help.aliyun.com/zh/yunxiao/developer-reference/getbranch-query-branch-information)
