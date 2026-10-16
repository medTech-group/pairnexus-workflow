# The can't-decide fallback without Python (#56): what the guard's hook command
# decides in an attended session when `python3` is missing or failing (a stub,
# a shim with no version), so the kit can't run at all. Run with `sh`, the
# PreToolUse event on stdin, by the hook command (`vendor.hook_command`), in a
# vendored project and in the plugin alike.
#
# The same rule as `fallback.py` (#53), read from the event's raw text:
# - a push or a merge is asked: `git` then `push`, or `gh` then `pr` then
#   `merge`, as whole words within one part of a Bash command (split at
#   ; & | and newlines, a `\` line continuation joined first), or a GitHub MCP
#   tool ending in merge_pull_request, push_files, create_or_update_file or
#   delete_file;
# - it is refused in solo mode (the profile's first plain `ruleset = …` line
#   says false) or in a permission mode where nobody is asked (`modes.py`:
#   bypassPermissions, dontAsk, or any value the kit doesn't know);
# - everything else is left alone: nothing is printed.
# Only the command is read, never the words elsewhere in the event (a file's
# content). Matched word by word (split, then compare), so it stays linear on
# any input. POSIX sh and awk only: it runs where nothing else of the kit can.
# It never prints anything but a decision, and the hook command exits 0 after it.

PROFILE_TOML="${CLAUDE_PROJECT_DIR:-.}/.claude/workflow/profile.toml"
export PROFILE_TOML
exec awk '
BEGIN { RS = "\001" }  # a JSON event holds no raw control characters: read it whole
{ ev = ev $0 }
END {
    tool = plain("tool_name")
    what = ""
    if (tool ~ /^mcp__/ && tolower(tool) ~ /github/) {
        if (tool ~ /merge_pull_request$/) what = "merge"
        else if (tool ~ /(push_files|create_or_update_file|delete_file)$/) what = "push"
    } else if (tool == "Bash") {
        what = push_or_merge(command())
    }
    if (what == "") exit 0

    head = "The workflow'"'"'s guard isn'"'"'t working, so it couldn'"'"'t check this " what ": python3 couldn'"'"'t run the workflow kit (it is missing or failing). To fix it: check that `python3 --version` runs and says 3.11 or newer, then start a new session."
    if (tool == "Bash") by_hand = "Or run it yourself in your own terminal (the command isn'"'"'t repeated here, since nothing could check it)."
    else by_hand = "Or do it yourself on GitHub."
    mode = permission_mode()
    if (solo()) {
        out("deny", head "\\nIn solo mode (`ruleset = false` in the profile) a push or a merge the guard can'"'"'t check is refused.\\n" by_hand)
    } else if (mode == "bypassPermissions" || mode == "dontAsk") {
        out("deny", head "\\nThe kit would have asked you about this, but nobody is asked in the `" mode "` permission mode, so it was refused.\\nTo be asked, switch the permission mode (Shift+Tab, or the mode selector).\\n" by_hand)
    } else if (mode != "" && mode != "default" && mode != "acceptEdits" && mode != "auto" && mode != "plan") {
        out("deny", head "\\nThe kit would have asked you about this, but the permission mode is one the kit doesn'"'"'t know, so it counts as one where nobody is asked and this was refused. Tell the kit'"'"'s maintainers about this mode.\\nTo be asked, switch the permission mode (Shift+Tab, or the mode selector).\\n" by_hand)
    } else {
        out("ask", head " Allow it only if you mean to.")
    }
}

# The first "name": "…" string value without escapes (a tool name, a mode).
function plain(name,    s) {
    if (!match(ev, "\"" name "\"[ \t\r\n]*:[ \t\r\n]*\"[^\"\\\\]*")) return ""
    s = substr(ev, RSTART, RLENGTH)
    match(s, /"[^"]*$/)
    return substr(s, RSTART + 1)
}

# The permission mode: "" when absent or null (a mode that asks), the value
# when a plain string, and "?" (a mode the kit doesn'"'"'t know) for anything else.
function permission_mode(    m, rest) {
    if (!match(ev, "\"permission_mode\"[ \t\r\n]*:[ \t\r\n]*")) return ""
    rest = substr(ev, RSTART + RLENGTH)
    if (substr(rest, 1, 4) == "null") return ""
    if (substr(rest, 1, 1) != "\"") return "?"
    m = plain("permission_mode")
    return (substr(rest, length(m) + 2, 1) == "\"") ? m : "?"
}

# The Bash command: the first "command" string value, decoded far enough to
# split it (escaped quotes and backslashes kept apart from the real ones,
# \n a newline, other escapes a space), up to its closing quote or, in a
# truncated event, the end.
function command(    s, i) {
    if (!match(ev, "\"command\"[ \t\r\n]*:[ \t\r\n]*\"")) return ""
    s = substr(ev, RSTART + RLENGTH)
    gsub(/\\\\/, "\002", s)   # an escaped backslash: a literal one
    gsub(/\\"/, "\003", s)    # an escaped quote: not the end
    i = index(s, "\"")
    if (i) s = substr(s, 1, i - 1)
    gsub(/\\n/, "\n", s)
    gsub(/\\./, " ", s)
    gsub("\002\n", " ", s)    # a line continuation joins its lines
    return s
}

function push_or_merge(cmd,    parts, n, i) {
    n = split(cmd, parts, /[;&|\n]/)
    for (i = 1; i <= n; i++) if (in_order(parts[i], "git push")) return "push"
    for (i = 1; i <= n; i++) if (in_order(parts[i], "gh pr merge")) return "merge"
    return ""
}

# The words of `seq`, in order, each a whole word of `part`.
function in_order(part, seq,    words, want, n, k, i, j) {
    n = split(part, words, /[^A-Za-z0-9_]+/)
    k = split(seq, want, " ")
    j = 1
    for (i = 1; i <= n && j <= k; i++) if (words[i] == want[j]) j++
    return j > k
}

# Solo mode: the profile'"'"'s first plain `ruleset = <word>` line says false.
function solo(    f, line, first, word) {
    f = ENVIRON["PROFILE_TOML"]
    RS = "\n"  # the profile line by line (the event was read whole)
    first = 1
    while ((getline line < f) > 0) {
        if (first) { while (substr(line, 1, 3) == "\357\273\277") line = substr(line, 4); first = 0 }
        if (line ~ /^[ \t]*ruleset[ \t]*=[ \t]*[A-Za-z0-9_]/) {
            sub(/^[ \t]*ruleset[ \t]*=[ \t]*/, "", line)
            match(line, /^[A-Za-z0-9_]+/)
            word = substr(line, 1, RLENGTH)
            close(f)
            return word == "false"
        }
    }
    close(f)
    return 0
}

function out(decision, reason) {
    printf "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"%s\",\"permissionDecisionReason\":\"%s\"}}\n", decision, reason
}
'
