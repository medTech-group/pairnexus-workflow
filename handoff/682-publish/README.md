# Publishing spec #682's breakdown (hand-off)

Everything here was settled and checked in an earlier session (edit round 16, answers 72–75, is already posted on #682; answers 76–88 are in the files below). That session lost its GitHub tools before it could publish. Publish these exactly as written, in this order, on medTech-group/pairnexus-workflow. Nothing here is to be redrafted or re-checked.

1. Comment `1-post-reread-16.md` on #682.
2. Comment `2-post-breakdown-check.md` on #682.
3. Comment `3-post-breakdown-reread.md` on #682.
4. Replace #682's body with `4-spec-682-body.md` (keep its title and labels `spec`, `ready-for-agent`).
5. Comment `5-post-breakdown-to-publish.md` on #682.
6. Create the 10 tickets in `6-tickets.json`, in its order (T1 to T10, blockers first): title and body as given, label `ready-for-agent`, each a sub-issue of #682. In each body, swap every `- T<n>` line under `## Blocked by` for `- #<number>` of the ticket created for T<n>. T10 keeps its `#273` line.
7. Comment on #682: "Breakdown published: T1 #a, T2 #b, …" with the numbers, ending with `<!-- workflow:agent -->` and the Claude Code footer.
8. Comment `8-post-planning-counts.md` on #682.

Skip any step already done (a comment already on #682 with the same heading, a ticket whose title already exists under #682). This folder lives only on the branch `claude/zealous-feynman-kpkxg0` and is never merged.
