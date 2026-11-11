# GitHub Repo Publish

A portable [Agent Skill](https://agentskills.io/specification) for first-time publishing of local Git projects to GitHub. It previews the target and files to publish, drafts a description and topics for review, and verifies the pushed commit. Interrupted publishes can be resumed.

## Install

Copy the entire skill folder, including `SKILL.md`, `scripts/`, and `references/`, to a skills directory your agent reads. Name the copied folder `github-repo-publish`.

| Client | Project skill directory | How to start |
| --- | --- | --- |
| [Codex](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills) | `.agents/skills/github-repo-publish/` | Invoke `$github-repo-publish` in chat. |
| [Claude Code](https://code.claude.com/docs/en/skills#choose-where-skills-load) | `.claude/skills/github-repo-publish/` | Run `/github-repo-publish`. |
| [Cursor](https://cursor.com/docs/skills#skill-directories) | `.agents/skills/github-repo-publish/` | Type `/` in Agent chat and select the skill. |
| [Gemini CLI](https://geminicli.com/docs/cli/skills/) | `.agents/skills/github-repo-publish/` | Check `/skills list` and ask Gemini to use the skill by name. |
| [OpenCode](https://opencode.ai/docs/skills/#discovery) | `.agents/skills/github-repo-publish/` | Ask OpenCode to load and use the skill by name. |

The four clients that read `.agents/skills/` can share a single copy in the project. Other clients that support the Agent Skills format can load the same folder from their documented skills directory. `agents/openai.yaml` supplies optional interface metadata for Codex.

## Use

Run the agent where it can access the source project and an authenticated GitHub CLI session. The publishing script uses Git, `gh`, and Python 3.8+ on macOS or Linux. It uses the GitHub account you select, with SSH or HTTPS for the push. See the [GitHub operations guide](references/github.md) for authentication and command details.

Ask the agent to prepare a preview before it publishes:

> Use github-repo-publish to preview publishing this project. Suggest a description and topics, let me choose the owner and repository name, and wait for my confirmation.

The skill uses the client's native question interface when available. For example, Codex can use structured questions and Claude Code can use `AskUserQuestion`. In a chat-only client, the same choices appear as text. The website is optional, and the complete preview is shown before you confirm the publish.
