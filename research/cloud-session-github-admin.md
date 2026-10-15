# Can a cloud session create a ruleset and change merge settings?

Research for [#14](https://github.com/medTech-group/pairnexus-workflow/issues/14) (map [#13](https://github.com/medTech-group/pairnexus-workflow/issues/13), destination item 4: automated GitHub set-up). Checked 15 Oct 2026.

## The question

Can a claude.ai cloud session, through the access it has (the Claude GitHub App behind the session's GitHub proxy, `gh`, and the GitHub MCP tools):

- create a repository ruleset: `POST /repos/{owner}/{repo}/rulesets`;
- change the merge settings: `PATCH /repos/{owner}/{repo}` with `allow_auto_merge` and `allow_merge_commit`?

And: what permission does each need, what does a refusal look like, and does a local session using the owner's own `gh` differ?

## The answer

| Path | Ruleset (`POST …/rulesets`) | Merge settings (`PATCH /repos/…`) |
| --- | --- | --- |
| Cloud session, `gh api` through the GitHub proxy | **Unknown; not something to plan on.** It needs the App to hold Administration: write on the installation and the proxy to pass the method and path. Neither is documented, and only a write would show it. | **Unknown**, for the same two reasons. |
| Cloud session, GitHub MCP tools | **No.** No tool for rulesets. | **No.** No tool for repository settings. |
| Local session, the owner's own `gh` | **Yes**, if the owner is a repo admin (classic `repo` scope; Admin role). | **Yes**, if the owner is a repo admin or maintainer. |

**What this means for item 4:** build the automated set-up for a **local session with the owner's own `gh`**. Keep the click-by-click steps as the fallback. A cloud session can still *read* everything `workflow doctor` needs: the rulesets and the merge settings.

There is also a design reason, beyond access, to keep these writes out of cloud sessions. A credential that can create a ruleset can also disable or delete one, and the kit counts on the ruleset to stop agents (`docs/enforcement.md`, §1 and the guard's "never … its rulesets … through the API"). So even if the App turns out to hold Administration: write, sessions should not use it.

## Permissions each endpoint needs

| Endpoint | GitHub App / fine-grained permission | User role (classic token, or the user behind an App user token) |
| --- | --- | --- |
| `POST /repos/{o}/{r}/rulesets` | Administration: **write** [1] | Admin: "Manage branch protection rules and repository rulesets" is Admin only [4] |
| `PUT /repos/{o}/{r}/rulesets/{id}` | Administration: **write** [1] | Admin [4] |
| `PATCH /repos/{o}/{r}` | Administration: **write** [1] | "Configure pull request merges": Maintain and Admin [4] |
| `GET /repos/{o}/{r}/rulesets`, `…/rulesets/{id}` | Metadata: read [1] | Any role can view rulesets [4] |
| `GET /repos/{o}/{r}` merge fields (`allow_auto_merge`, …) | "To view merge-related settings, you must have the contents:read and contents:write permissions" [2] | |

How an App user token is limited: "The app can only access resources that the user has access to", "The app can only access resources that it has permission to access", and "A token cannot grant additional access capabilities to a user" [3]. So a cloud session can write a ruleset only if both are true:

- the Claude App's installation holds Administration: write;
- the connected GitHub user is an Admin of the repo.

`gh auth login`: "The minimum required scopes for the token are: `repo`, `read:org`, and `gist`" [5]. The classic `repo` scope covers these endpoints, and the user's role decides the rest. The REST page for rulesets names no scope [6]. **Unverified:** that `repo` alone is enough for `POST …/rulesets` with a classic token. This is the usual rule for repo endpoints, but no page states it for this endpoint.

## Cloud session: what the proxy and the App allow

### Documented

Anthropic's docs describe the GitHub proxy [7]:

- "all GitHub operations go through a dedicated proxy that keeps your real GitHub credentials outside the session's VM".
- "requests from the built-in GitHub tools, and from `gh` under the `proxy-injected` placeholder, go out with your real credentials substituted".
- It is limited to the attached repositories: "An API request for another repository gets a 403 whose message starts with `GitHub access to` and contains `is not enabled for this session`".
- GraphQL is refused with a 403 starting "`GitHub GraphQL is not available from Claude Code sessions`".
- On pushes: "the proxy rejects branch deletions and pushes of anything other than a branch … It doesn't limit which branches a push can update. To do that, use branch protection rules or rulesets on GitHub."

The credential is either:

- the Claude GitHub App (the browser onboarding); or
- the user's own `gh` token sent with `/web-setup` [8].

The docs do not say which REST paths or methods the proxy allows. They also don't publish the Claude App's permission list:

- The app page [9] lists none.
- The `claude-code-action` set-up guide gives a custom app's minimum, "Contents: Read & Write", "Issues: Read & Write", "Pull requests: Read & Write", and says nothing of Administration [10].

### Observed from this session (read-only calls, 15 Oct 2026)

This session is a cloud session on `medTech-group/pairnexus-workflow`. It was connected through the GitHub App and has no token of its own. Observations:

- **`GH_TOKEN` is the placeholder.** Its value starts `prox…`, which matches `proxy-injected` [7], and `gh auth status` reports it invalid. Responses carry:
  - `X-Oauth-Client-Id: Iv23liqTIFEtdIu6Vn1r`, a GitHub App client id (the `Iv23` prefix);
  - an empty `X-Oauth-Scopes`;
  - a `Github-Authentication-Token-Expiration` header.

  So the proxy sends a **GitHub App user access token**. **Unverified:** that this client id is "Claude" and not another Anthropic app.
- **The user has admin.** `gh api repos/medTech-group/pairnexus-workflow --jq .permissions` gives `admin: true`. This is the *user's* role, not the App's permissions [3].
- **The App holds at least Administration: read.**
  - `GET …/rulesets/rule-suites` returned 200, with `X-Accepted-GitHub-Permissions: administration=read`.
  - `GET …/branches/main/protection` returned 404 "Branch not protected", with `X-Accepted-GitHub-Permissions: administration=read`. That is GitHub's answer once the permission check has passed. A token without the permission gets "Resource not accessible by integration" [11].
  - Whether the App has Administration **write** can't be read from any GET.
- **Rulesets and merge settings read fine.**
  - `GET …/rulesets` → 200, listing `merge-rule` (`enforcement: active`).
  - `GET …/rulesets/24927238` → 200.
  - `GET /repos/…` gives `allow_auto_merge: true` and `allow_merge_commit: true`, which means the token also has contents: write [2].
- **The proxy allowlists paths, beyond what the docs say.** Each of these got a 403 from the proxy, not from GitHub:
  - `GET …/keys`, `…/autolinks`, `…/hooks`, `…/collaborators`, `…/environments`, `…/vulnerability-alerts`: `"Access to this GitHub API path is not permitted through this proxy."`
  - `GET …/actions/permissions` and `…/actions/secrets`: `"Access to this GitHub Actions path is not permitted through this proxy."`
  - `GET /user/installations` and `GET /apps/claude`: `"This GitHub API path is not available: sessions are bound to their configured repositories. Use repository-scoped endpoints (repos/{owner}/{repo}/...)."`

  So whether `POST …/rulesets` or `PATCH /repos/…` passes the proxy is its own unknown, apart from the App's permissions.
- **The GitHub MCP tools** in this session have no tool for rulesets or repository settings. The list was searched for "ruleset", "repository settings", "update" and "merge": the nearest are `merge_pull_request`, `enable_pr_auto_merge` (per PR, not the repo setting), `update_pull_request` and `create_repository`. So that path is a no, whatever the token holds.

## What a refusal looks like

| Who refuses | Status and body | When |
| --- | --- | --- |
| Claude's GitHub proxy, path not allowed | 403 `{"message":"Access to this GitHub API path is not permitted through this proxy."}` (Actions paths: "…GitHub Actions path…") | Observed on GETs above |
| Claude's GitHub proxy, not repo-scoped | 403 `"This GitHub API path is not available: sessions are bound to their configured repositories…"` | Observed |
| Claude's GitHub proxy, another repo | 403 starting `GitHub access to` … `is not enabled for this session` | Documented [7] |
| Claude's GitHub proxy, GraphQL | 403 starting `GitHub GraphQL is not available from Claude Code sessions` | Documented [7] |
| GitHub, App lacks the permission | 403 `"Resource not accessible by integration"`; `X-Accepted-GitHub-Permissions` names what is needed, e.g. `administration=write` | Documented [11] |
| GitHub, user lacks the role | 403, or 404 where GitHub hides the resource ("GitHub uses a `404 Not Found` response instead of a `403 Forbidden`") | Documented in general [11]; the exact body for these two endpoints is unverified |

These refusals look different, so a set-up script can tell them apart:

- A proxy refusal has a message naming the proxy or the session. It has no `X-Accepted-GitHub-Permissions` header and no `X-Github-Request-Id`, as observed.
- A GitHub refusal carries both headers.

The proxy's 403 body links to `docs.anthropic.com/en/docs/claude-code/github-actions`.

## Local session with the owner's own `gh`

This path is different: no proxy is in the way, and the token is the owner's own.

- `gh auth login` tokens carry `repo` (and `read:org`, `gist`) [5].
- If the owner is a repo Admin, both writes are allowed:
  - rulesets: Admin only [4];
  - merge settings: Maintain or Admin [4].
- A fine-grained PAT would need Administration: write [1].
- An organisation can restrict classic tokens or require SSO authorisation. Then `gh` gets GitHub's own 403 with a message saying so. **Unverified** for medTech-group.

`/web-setup` sends that same local `gh` token to claude.ai for cloud sessions [8]. Even so, a cloud session's request still goes through the proxy, and the path allowlist observed above still applies. **Unverified:** whether the proxy treats a `/web-setup` token's write requests differently.

## Unverified, and how to settle it

1. **Does the Claude App's installation hold Administration: write?**
   - Ask the owner to look in GitHub → medTech-group → Settings → GitHub Apps → Claude → Configure (the permissions it was granted).
   - Or look at the install prompt on `github.com/apps/claude`.
   - A session can't read it: `/user/installations` and `/apps/claude` are refused by the proxy.
2. **Does the proxy pass `POST …/rulesets` and `PATCH /repos/{o}/{r}`?** Only a write shows it. The least risky probe is a request that GitHub refuses before writing anything, for example `POST …/rulesets` with a body that isn't valid JSON (GitHub answers 400 "Problems parsing JSON"). The response would tell three cases apart:
   - a proxy 403 (path refused);
   - "Resource not accessible by integration" (App lacks write);
   - 400/422 (both pass).

   This research made no write. The owner may choose to authorise that probe.
3. That `Iv23liqTIFEtdIu6Vn1r` is the Claude GitHub App.
4. That a classic `repo` scope suffices for `POST …/rulesets` (no page states the scope for this endpoint).
5. The exact refusal body when the user lacks the Admin role.

## Sources

1. GitHub Docs, "Permissions required for GitHub Apps", Repository permissions for "Administration" (`POST /repos/{owner}/{repo}/rulesets`, `PUT …/rulesets/{ruleset_id}`, `PATCH /repos/{owner}/{repo}`: write; `GET …/branches/{branch}/protection`, `GET …/rulesets/rule-suites`: read) and for "Metadata" (`GET …/rulesets`: read). https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps?apiVersion=2022-11-28
2. GitHub Docs, REST "Repositories": Get a repository ("To view merge-related settings, you must have the contents:read and contents:write permissions"); Update a repository (`allow_auto_merge`, `allow_merge_commit`; responses 200, 307, 403, 404, 422). https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#update-a-repository
3. GitHub Docs, "Authenticating with a GitHub App on behalf of a user". https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-with-a-github-app-on-behalf-of-a-user
4. GitHub Docs, "Repository roles for an organization" (Manage branch protection rules and repository rulesets: Admin; Configure pull request merges: Maintain, Admin; View rulesets: all roles). https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization
5. GitHub CLI manual, `gh auth login`. https://cli.github.com/manual/gh_auth_login
6. GitHub Docs, REST "Rules for repositories" (Create a repository ruleset: 201, 404, 422, 500). https://docs.github.com/en/rest/repos/rules?apiVersion=2022-11-28
7. Claude Code docs, "Configure cloud environments": GitHub proxy; Work with GitHub issues and pull requests. https://code.claude.com/docs/en/cloud-environments
8. Claude Code docs, "Use Claude Code in the cloud": GitHub authentication options; Security and isolation. https://code.claude.com/docs/en/claude-code-on-the-web
9. The Claude GitHub App's page. https://github.com/apps/claude
10. `anthropics/claude-code-action`, `docs/setup.md` (custom app's minimum permissions). https://github.com/anthropics/claude-code-action/blob/main/docs/setup.md
11. GitHub Docs, "Troubleshooting the REST API" ("Resource not accessible by integration"; `X-Accepted-GitHub-Permissions`; 404 in place of 403). https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api
