# Which host gives a free preview deploy per PR, and how does it fit?

Research for [#18](https://github.com/medTech-group/pairnexus-workflow/issues/18) (map [#13](https://github.com/medTech-group/pairnexus-workflow/issues/13), destination items 6 and 8). Checked 15 Oct 2026, against each host's own docs and pricing pages. Numbers in brackets are the sources at the end.

## The question

For Vercel, Netlify and Cloudflare (and any other clearly competitive host):

- the free tier, its limits, and any limit on commercial use;
- the set-up steps, and whether a non-builder can do them;
- how the preview link reaches the PR;
- what secrets it needs and where they live, given that ticket sessions hold no credentials (`docs/enforcement.md` §2: "No secrets: … no deploy tokens");
- full-stack support (server functions, a database) or static only;
- privacy: are previews public, and can they be protected;
- how it fits a starter's CI and the profile's `[sensitive]` rules.

## The answer

**Recommend Cloudflare, through its own GitHub App** (Workers Builds with Worker Previews; Pages for a purely static site). It is the only one of the three whose free tier:

- allows commercial use (Vercel's Hobby does not [5]);
- builds a private repository's PR whoever authored the commits. This matters because the kit's cloud sessions commit as `Claude <noreply@anthropic.com>` (observed, below). Vercel's Hobby deploys a private repo only for commits by the Hobby team's owner [6], and Netlify's Free holds a deploy from an unrecognised author for the owner's approval [13];
- runs server code with a free database (Workers and D1 [20]).

Its previews are **public by default** [17][21]. So the starter must either keep previews on synthetic data only, or turn on Cloudflare Access (free for up to 50 users [24]).

### Comparison

| | **Cloudflare** (Workers Builds / Pages) | **Vercel** (Hobby) | **Netlify** (Free) |
|---|---|---|---|
| Price of the free tier | $0. Workers: 100,000 requests a day, 10 ms CPU per request [20]. Workers Builds: 3,000 build minutes a month, 1 at a time [19]. Pages: 500 builds a month [16] | $0. 100 deployments a day, 1M function invocations, 100 GB transfer a month [4] | $0. 300 credits a month, a hard limit [10][11]. Deploy Previews cost 0 credits; only production deploys (15) and traffic and compute use them [11] |
| When the free tier runs out | Further requests of that kind fail until the daily reset [20] | Wait 30 days to use the feature again [4] | "all of your web projects … are paused" [11] |
| Commercial use | No commercial-use limit found in the Self-Serve Subscription Agreement; it bars reselling access and taking card details on a free-plan site [23] | **Not allowed**: "Hobby teams are restricted to non-commercial personal use only" [5] | No commercial-use limit in the agreement's Free Usage Tier section, which Netlify may end "without notice" [14] |
| Private repo in a GitHub organisation, commits by Claude | No author rule found (unverified that none exists) | **Blocked**: Hobby "does not support collaboration for private repositories"; "the commit author must be the owner of the Hobby team" [6] | **Held**: "Pending approval" until the Team Owner approves the author [13]. Free has no Git Contributors for private repos [12] |
| Set-up for a non-builder | Dashboard: Import a repository, install the "Cloudflare Workers and Pages" GitHub App (org owner or GitHub Apps Manager) [18][19b] | Dashboard: import the repo, Vercel for GitHub app [3] | Dashboard: new site from Git, install the Netlify GitHub App [9] |
| How the link reaches the PR | Workers Builds: a **PR comment** with the Preview URL, and a **check run** [18]. Pages: a preview URL and status checks; whether it comments is not stated [15][17] | A **PR comment**, a **commit status**, and a **GitHub Deployment** [3] | A **commit status**, a **PR comment** and **commit checks**, all on by default [8] |
| Repo secret needed | None (the host's App) | None (the host's App) | None (the host's App) |
| Full-stack | Yes: Workers with D1 (5 GB), KV, R2, Durable Objects [20][21] | Yes: functions up to 300 s [4] | Yes: functions; compute uses credits [10] |
| Preview environment per PR | Worker Previews: own URL per branch, updated per push; Durable Objects isolated per Preview; D1/KV/R2 only if bound to a separate resource; 100 Previews per Worker on Free [21][22] | One preview URL per PR's latest push [3] | One Deploy Preview per PR [7] |
| Previews public by default? | **Yes** [17][21] | **No**: Vercel Authentication on by default for new projects [2b] | Depends on the team: teams made on or after 28 Jul 2026 default to private [25] |
| Protecting previews on the free tier | Cloudflare Access: free for up to 50 users [24] | Vercel Authentication, **1** outside viewer and **1** shareable link per account [2][2c] | Private: "only be seen by the Team Owner" on Free; no password protection [25][26] |
| Fork PRs | Pages: no preview [15] | Needs authorisation by a team member [3] | Public repos: untrusted deploys (forks) wait for a site member's approval by default [27] |

### Ruled out, and why

- **Vercel Hobby**: three separate blockers. It's non-commercial only [5]. It won't deploy a private org repo's commits by anyone but the Hobby team's owner [6]. And its free protection admits one outside viewer [2], so a non-builder can't hand a preview to a colleague without making it public. Vercel Pro removes all three, at $20 per developer seat a month [4]. Vercel is the best fit for a team already paying for it.
- **Netlify Free** allows commercial use [14] and previews cost no credits [11]. But on a private repo, every Claude-authored PR is held for the Team Owner's approval [13]. Free has no Git Contributors for private repos [12], and a private preview can be seen only by the Team Owner [25]. Netlify does treat "bots from GitHub Marketplace" as recognised authors [13]. Whether Claude's commits count as that is unverified. Running out of credits pauses every site [11].
- **Others** (GitHub Pages, Render, Fly.io, Railway) were not assessed: none of them was clearly competitive at $0 for per-PR previews of a full-stack app with a GitHub App and no repo secret. Treat this as a gap, not a finding.

## How it fits the kit

### Secrets: host-side App, not CI tokens

There are two ways to get a preview per PR:

1. **The host's GitHub App builds it** (all three hosts). The host holds the build. Its environment variables and secrets live in the host's dashboard, or in the Wrangler `previews` block plus `wrangler secret` commands [21]. **No secret goes into GitHub or into any Claude environment.** Ticket sessions keep holding nothing (`docs/enforcement.md` §2).
2. **CI deploys it** with a host token stored as a GitHub Actions secret, for example `wrangler preview` in a workflow [22], or `vercel deploy --prebuilt --token=${{ secrets.VERCEL_TOKEN }}` [3]. Ticket sessions still never see the token: only CI does. But a non-builder must create a token and paste it into repo settings. A secret also doesn't reach workflows from forks or Dependabot ("secrets are not passed to the runner when a workflow is triggered from a forked repository"; Dependabot PRs "are treated as though they are from a forked repository") [28][29]. And the workflow becomes a place a credential can leak.

**Use (1) for the starter.** It is clicks only, and it keeps every credential outside the repository and the sessions. Keep (2) as the documented fallback for repos that can't install a third-party App.

### How the link reaches the PR, and how the kit reads it

With Workers Builds, the link arrives as a PR comment from Cloudflare's App, and the build as a check run [18]. A ticket session or the merge helper (item 6) can read either with `gh` through the session's GitHub proxy. That is a read of the session's own repo, which needs no credential in the session.

GitHub check runs come from GitHub Apps; commit statuses come from external services [30]. A required check must pass before merging [30], so:

- **Don't add the host's check to `required_checks` at first.** A host outage or a used-up free quota would then block every merge. Item 6's merge helper can show the link and the host check's state beside CI's verdict instead.

### `[sensitive]` rules and previews

`[sensitive].patterns` are checked "against every GitHub post" that a session makes (`docs/profile.md`). The host's PR comment is posted by the host's App, not by a session, so the guard never sees it. That's fine: it holds a URL and a build status, nothing from the app's data.

The real exposure is **what the preview serves**. A public preview of an app that reads real data publishes that data. So:

- The starter's previews use **synthetic seed data only**, in a database bound for previews and kept apart from production (D1 isn't isolated per Preview unless bound to a separate resource [21]).
- A profile that declares `[sensitive]` patterns should also say "protect previews". On Cloudflare that is an Access policy over the account's or the Worker's previews [21][24]. A non-builder's colleague then signs in by email. **Unverified:** the exact Access set-up steps and whether its free plan needs a payment method.

### Which Cloudflare product

- **Workers Builds with Worker Previews** suits a full-stack starter. Each PR gets a stable URL updated per push, a PR comment and a check run [18][21][22]. Cloudflare says Workers "has a distinctly broader set of features" than Pages [31]. Previews need Wrangler 4.135.0 or later [21]. They come from builds of non-production branches once **Enable Preview Builds** is on [19c]; whether it is on by default isn't stated.
- **Pages** is simpler for a static site, but it makes no preview for PRs from forks [15].

## What's unverified

1. **That Cloudflare builds Claude-authored commits on a private org repo without an author check.** No page says it does; none says it doesn't. Test it on a demo repo.
2. **Vercel and Netlify applied to `Claude <noreply@anthropic.com>`.** The commit author is observed in this repo (`git log` on `origin/main`: the kit's commits are authored `Claude <noreply@anthropic.com>`, the merges by the owner). Vercel compares the commit author with the Hobby owner's login connection [6]. Netlify recognises Marketplace bots [13]. Whether Claude's commits are matched to the Claude GitHub App is untested.
3. **Whether Workers Builds' "Enable Preview Builds" is on by default**, and how Workers Builds treats PRs from forks [19c].
4. **Cloudflare Access's free plan**: whether a card is required and the exact clicks. The 50-user figure is from Cloudflare's product page [24], not the docs.
5. **Whether Cloudflare Pages comments on the PR**, or only shows a status [15][17].
6. **Netlify Free's commercial use**: the agreement doesn't forbid it [14], but no page says "allowed" outright.
7. **Free-tier figures change.** Netlify's credit model and Vercel's limits were both changed within the last year; recheck before the starter ships.

## Open points for the map

- **Item 7 (starter):** pick a Cloudflare Workers stack (Workers + D1 + static assets) so previews come free. Ship a `wrangler` config with a `previews` block bound to a preview-only database, plus a seed script with synthetic data.
- **Item 6 (judging a PR):** the merge helper reads the host's PR comment or check run for the link. Decide which, and what it says when the preview failed or is missing.
- **Profile:** a small `[preview]` table (for example `host`, `protected = true|false`) so `workflow doctor` (item 3) can check it and the guided start can explain it. Or leave it out until the starter needs it.
- **A demo-repo test** for unverified points 1 to 3, alongside item 10's trust gate.

## Sources

1. Vercel, Pricing (Hobby: unlimited deployments; 1M invocations; 100 GB; "personal, non-commercial use"). https://vercel.com/pricing
2. Vercel Docs, "Restrict access to deployments with Vercel Authentication" ("Those on the Hobby plan can only have one external user per account"; who can access). https://vercel.com/docs/deployment-protection/methods-to-protect-deployments/vercel-authentication
   - 2b. Vercel Changelog, "Deployment Protection is now enabled by default for new projects" (2 Nov 2023): "For all new deployments, Deployment Protection with Vercel Authentication is now enabled by default." https://vercel.com/changelog/deployment-protection-is-now-enabled-by-default-for-new-projects
   - 2c. Vercel Docs, "Usage & Pricing for Deployment Protection" (Shareable Links on Hobby: "Included, limited to one link per account"; Password Protection: "Not available" on Hobby). https://vercel.com/docs/deployment-protection/usage-and-pricing
3. Vercel Docs, "Deploying GitHub Projects with Vercel" (PR comment; GitHub Deployments API; commit status; fork authorisation; GitHub Actions with `VERCEL_TOKEN`). https://vercel.com/docs/git/vercel-for-github
4. Vercel Docs, "Vercel Hobby Plan" (included usage; 100 deployments a day; 300 s functions; wait 30 days; $20 per developer seat on Pro). https://vercel.com/docs/plans/hobby
5. Vercel Docs, "Fair Use Guidelines", Commercial usage ("Hobby teams are restricted to non-commercial personal use only"). https://vercel.com/docs/limits/fair-use-guidelines
6. Vercel Docs, "Troubleshoot project collaboration", Hobby teams ("does not support collaboration for private repositories"; "the commit author must be the owner of the Hobby team"). https://vercel.com/docs/deployments/troubleshoot-project-collaboration
7. Netlify Docs, "Deploy Previews" (status on the PR; comment with deploy notifications; `X-Robots-Tag: noindex`). https://docs.netlify.com/site-deploys/deploy-previews/
8. Netlify Docs, "Deploy notifications" (commit statuses, PR comments, commit checks "added to all new GitHub-connected Netlify sites by default"). https://docs.netlify.com/deploy/deploy-notifications/
9. Netlify Docs, "Repository permissions and linking" (Netlify GitHub App; "generated, limited-scope tokens that expire after one hour"; checks API). https://docs.netlify.com/build/git-workflows/repo-permissions-linking/
10. Netlify, Pricing (Free: 300 credits; credit costs per meter; "Unlimited deploy previews"). https://www.netlify.com/pricing/
11. Netlify Docs, "How credits work" (300 credits a month, reset each cycle; Deploy Previews 0 credits; projects paused when used up). https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/how-credits-work/
12. Netlify Docs, "Credit-based pricing plans" (Git Contributors for private repositories: N/A on Free; password protection: N/A on Free; Pro from $20/month). https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/credit-based-pricing-plans/
13. Netlify Docs, "Deploy overview", Deploy Request Policy ("only builds and deploys changes pushed to private repositories from recognized authors"; "Pending approval"; "bots from GitHub Marketplace as recognized authors"). https://docs.netlify.com/deploy/deploy-overview/
14. Netlify, Self-Serve Subscription Agreement, §6 Free Usage Tier. https://www.netlify.com/legal/self-serve-subscription-agreement/
15. Cloudflare Docs, Pages "GitHub integration" (check runs; app shared with Workers; org owner or GitHub Apps Manager; "preview URLs will not be created for pull requests created from forks"). https://developers.cloudflare.com/pages/configuration/git-integration/github-integration/
16. Cloudflare Docs, Pages "Limits" (500 builds a month; 1 at a time; 20 minutes; 20,000 files; unlimited previews). https://developers.cloudflare.com/pages/platform/limits/
17. Cloudflare Docs, Pages "Preview deployments" ("By default, these deployment URLs are public"; access policy restricts to "your Cloudflare account"; branch aliases). https://developers.cloudflare.com/pages/configuration/preview-deployments/
18. Cloudflare Docs, Workers Builds "GitHub integration" (PR comment with Preview URL for builds that run `wrangler preview`; check runs). https://developers.cloudflare.com/workers/ci-cd/builds/git-integration/github-integration/
19. Cloudflare Docs, Workers Builds "Limits and pricing" (Free: 3,000 build minutes a month; 1 concurrent build; 20 minutes). https://developers.cloudflare.com/workers/ci-cd/builds/limits-and-pricing/
   - 19b. Cloudflare Docs, Workers "Builds" (Import a repository; Connect). https://developers.cloudflare.com/workers/ci-cd/builds/
   - 19c. Cloudflare Docs, Workers Builds "Build branches" ("Enable Preview Builds"; PR comments for non-production branches). https://developers.cloudflare.com/workers/ci-cd/builds/build-branches/
20. Cloudflare Docs, Workers "Pricing" (Free: 100,000 requests a day, 10 ms CPU; D1 5 GB, 5M rows read and 100,000 written a day; KV; daily reset, then errors). https://developers.cloudflare.com/workers/platform/pricing/
21. Cloudflare Docs, Workers "Previews" (Wrangler 4.135.0; 100 Previews per Worker on Free; `previews` block and secrets by command; D1/KV/R2 isolated only when bound separately; "Preview URLs are public by default. Use Cloudflare Access to require sign-in."). https://developers.cloudflare.com/workers/previews/
22. Cloudflare Changelog, "Test every pull request in an isolated environment with Worker Previews" (22 Sep 2026); "Workers Builds now posts preview URLs in seconds" (12 Oct 2026); Workers "Compare workflows" ("Do not use Version URLs for branch or pull request testing. Use Previews instead."). https://developers.cloudflare.com/changelog/post/2026-09-22-worker-previews/ · https://developers.cloudflare.com/changelog/post/2026-10-12-faster-pull-request-comments/ · https://developers.cloudflare.com/workers/previews/compare-workflows/
23. Cloudflare, Self-Serve Subscription Agreement (§2.2.1(a) no reselling access; §2.2.1(h) no card data on a free-plan site; §2.6 free services). https://www.cloudflare.com/terms/
24. Cloudflare, Access product page (Free: "$0", "forever", "Best for teams under 50 users", "50 user limit"). https://www.cloudflare.com/sase/products/access/
25. Netlify Docs, "Project visibility" (credit-based plans; default private for teams created on or after 28 Jul 2026; on Free "private projects can only be seen by the Team Owner"). https://docs.netlify.com/manage/security/secure-access-to-sites/project-visibility/
26. Netlify Docs, "Password protection" ("isn't available on Credit-based Free and Personal plans"). https://docs.netlify.com/manage/security/secure-access-to-sites/password-protection/
27. Netlify Docs, "Get started with environment variables", Sensitive variable policy ("only available for sites connected to public repositories"; "Require approval (default)"). https://docs.netlify.com/build/environment-variables/get-started/
28. GitHub Docs, "Using secrets in GitHub Actions" ("secrets are not passed to the runner when a workflow is triggered from a forked repository"; write access to create them). https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions
29. GitHub Docs, "Events that trigger workflows", `pull_request` (fork PRs: read-only `GITHUB_TOKEN`, no secrets; Dependabot PRs treated as forks; `pull_request_target` warning). https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows
30. GitHub Docs, "About status checks" (checks from GitHub Apps; commit statuses from external services; required checks must pass before merging). https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/about-status-checks
31. Cloudflare Docs, "Migrate from Pages to Workers" ("Unlike Pages, Workers has a distinctly broader set of features available to it"). https://developers.cloudflare.com/workers/static-assets/migration-guides/migrate-from-pages/
