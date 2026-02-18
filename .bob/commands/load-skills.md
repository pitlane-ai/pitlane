---
name: load-skills
description: Discover and load Agent Skills from .bob/skills/ or ~/.bob/skills/
icon: 🎯
category: productivity
tags:
  - skills
  - discovery
  - agentskills
---

# /load-skills - Agent Skill Discovery & Loading

Discover and progressively load Agent Skills (https://agentskills.io) that are already deployed in `.bob/skills/` (project) or `~/.bob/skills/` (global).

## When to Use

Use this command to discover and load Agent Skills that are already deployed in `.bob/skills/` or `~/.bob/skills/`.

**Typical workflow:**
1. User runs `/load-skills` command
2. Bob scans skill directories, loads front-matter into context, and presents available skills with descriptions
3. The user may continue working in any mode
4. During session, Bob identifies which skills are relevant based on user's task and loaded frontmatter in context
5. Bob asks for confirmation, then loads full instructions for selected skills
6. Bob follows the skills instructions to help the user complete their task

**Note:** Skills must already exist in `.bob/skills/` (project-specific) or `~/.bob/skills/` (user-global). This command discovers and loads existing skills, it does not create new ones.

## Instructions

### Skill Locations
- **Project:** `.bob/skills/`
- **Global:** `~/.bob/skills/`

### Progressive Loading (3 Stages)

#### 1. Metadata Loading (when /load-skills is invoked)
When user runs `/load-skills` command:
- List directories in `.bob/skills/`. Do NOT use your built-in tool for listing files. DO use ls or dir.
- List directories in `~/.bob/skills/`. Do NOT use your built-in tool for this. DO use ls or dir.
- For each dir with `SKILL.md`: read the frontmatter only. Start with the 20 lines of the files, and continue until reading the full frontmatter.
- Load ALL frontmatter metadata into context (~100 tokens/skill)
- Present skills grouped by project/global
- User may now continue working (metadata stays in context)

#### 2. Instructions Loading (during session, any mode)
When user's task matches a skill (based on loaded frontmatter):
- Identify relevant skills by comparing task keywords to descriptions in context
- Ask user for confirmation before loading
- After confirmation: read the complete `SKILL.md` (no line range)
- Load full instructions into context (<5000 tokens/skill)
- Note resource references (`scripts/`, `references/`, `assets/`)
- Follow skill instructions to help complete the task AS needed based on the SKILL instructions

#### 3. Resource Loading (just-in-time)
Load skill resources only when needed:
- Scripts when execution is required
- References when additional context is needed
- Assets when files need to be accessed

### Key Rules
- When `/load-skills` is invoked: Load ALL metadata at startup (stays in context)
- During session (any mode): Identify relevant skills from loaded metadata
- **ASK USER** before loading full skill instructions
- Activate only RELEVANT skills (1-3 max)
- Load resources JUST-IN-TIME
- Follow loaded skill instructions to complete tasks

### File Permissions
Can read and edit:
- `SKILL.md` files
- Files in `skills/` directories
- Files in `.bob/skills/` directories
- Files in `references/` directories
- Files in `scripts/` directories
- Files in `assets/` directories

Pattern: `(SKILL\.md|skills/.*/.*|\.bob/skills/.*/.*|references/.*|scripts/.*|assets/.*)$`
