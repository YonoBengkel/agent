# Global rules on this machine ({{FOLDER_KERJA}} projects)

Hermes copy of the project protocol in `{{FOLDER_KERJA}}\AGENTS.md`. It lives in SOUL.md because
Hermes reads `AGENTS.md` only from the git root down to the working folder, never from parent
folders such as `{{FOLDER_KERJA}}`. The text between the `sync` markers is written by
`{{WORKSPACE}}\tools\sync_rules.py`. Edit the source instead, then run the script.

**Scope: the sections below apply only inside `{{FOLDER_KERJA}}`. In any other working folder, ignore them.**

## Reading across projects

{{NAMA}} allows every agent on this machine to read ecosystem files: the vault at `{{VAULT}}\`,
the skill library at `{{WORKSPACE}}\skills\`, and other project repos under `{{FOLDER_KERJA}}\`.
The protected folders ({{DILINDUNGI}}) and secrets stay off-limits.

<!-- sync:begin {{LABEL}} -->
<!-- sync:end -->
