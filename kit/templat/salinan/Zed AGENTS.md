# Zed global rules ({{FOLDER_KERJA}} projects)

Zed copy of the project protocol in `{{FOLDER_KERJA}}\AGENTS.md`. It lives in Zed's global rules
because Zed reads `AGENTS.md` only in the opened workspace folder, not in parent folders. The
text between the `sync` markers is written by `{{WORKSPACE}}\tools\sync_rules.py`; edit the
source instead, then run the script.

**Scope: the sections below apply only inside `{{FOLDER_KERJA}}`. In any other workspace, ignore them.**

## Reading across projects

{{NAMA}} allows every agent on this machine to read ecosystem files: the vault at `{{VAULT}}\`,
the skill library at `{{WORKSPACE}}\skills\`, and other project repos under `{{FOLDER_KERJA}}\`.
If Zed's `read_file` refuses such a path because it is outside the open project, read it with the
`terminal` tool (PowerShell `Get-Content "<path>"`) instead of stopping to ask each time. The
protected folders ({{DILINDUNGI}}) and secrets stay off-limits.

<!-- sync:begin {{LABEL}} -->
<!-- sync:end -->
