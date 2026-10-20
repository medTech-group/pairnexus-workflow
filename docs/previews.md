# Add try-it links to your pull requests

**Once for each project.** After it, each [pull request](glossary.md#pull-request-pr) on your project gets a try-it link: a [preview link](glossary.md#preview-link) that opens a working copy of the change, so you can try it before you [merge](glossary.md#merge) it, without reading its code. Cloudflare builds each one for free and reports it on the pull request as a comment and a [check](glossary.md#checks-ci). Connecting Cloudflare this way puts no live site on the internet: you get previews only.

These are the steps of the "Add try-it links" upgrade (to come), written out to follow on your own. Your project needs a Wrangler config, the file (`wrangler.toml`, or `wrangler.json` or `wrangler.jsonc`) that tells Cloudflare how to run your app on Cloudflare Workers.

**Before step 2:** your Wrangler config must say `workers_dev = false`, and, for a project with sensitive data, `preview_urls = false`. If it doesn't yet, do step 6 first, with those values, and [merge](glossary.md#merge) its pull request. Connecting a [repository](glossary.md#repository) makes Cloudflare deploy (put online) its [`main`](glossary.md#main) too, and each deploy sets the Worker's public address and preview links from the config, so without them they are public at once.

## The steps

1. **A Cloudflare account:** sign up at [dash.cloudflare.com/sign-up](https://dash.cloudflare.com/sign-up). The free plan is enough.

2. **Connect your repository through Cloudflare's GitHub app:** in Cloudflare, go to **Workers & Pages**, create an application, and import a repository from GitHub. When GitHub asks where to install Cloudflare's app, choose **Only select repositories** and pick this repository alone, so Cloudflare sees nothing else. Cloudflare's own steps: [GitHub integration](https://developers.cloudflare.com/workers/ci-cd/builds/git-integration/github-integration/).

3. **An empty Build command, on Production and on Previews Base:** in your Worker's **Settings**, under **Build**, clear the **Build command** box in the build settings for **Production** and for **Previews Base**, and save both. A new project puts `npx wrangler deploy` there, which makes each preview try to deploy the live site instead, and fail.
   - **The trap:** "Previews Base" is a template. Each [branch](glossary.md#branch) copies it when it is first built, and keeps its copy. A branch built before you cleared the box keeps the old command, however often you retry its build. Push a fresh branch instead: ask Claude to open a new pull request from a new branch.

4. **A new build token:** where the build settings ask for an API token (the key Cloudflare's builds sign in with), choose **Create new token**. An old or reused token fails with "Configured API token unavailable".

5. **Preview URLs on:** they are off by default. In your Worker's **Settings**, under **Domains & Routes**, enable **Preview URLs**. While they are off, Cloudflare still builds each branch but says "Builds for Preview branches will run, but they will not create Preview URLs until you enable them", and no link arrives.
   - **With sensitive data,** do step 7 straight after this one, before any pull request is pushed: until Access is on, each preview is public. The config's `preview_urls = false` stays until step 7 is done.

6. **The Wrangler config: a `[previews]` block, and no live site.** Ask Claude to add or change these in your `wrangler.toml`, in a pull request:

   ```toml
   workers_dev = false
   preview_urls = true

   [previews]
   ```

   - `workers_dev = false` keeps your Worker's own public address off. Connecting a repository makes Cloudflare deploy `main` too, and this keeps that deploy off the internet, so there is no live site. If your config has `routes` or a custom domain, your project already has a live site, and connecting deploys `main` to it.
   - `preview_urls = true` keeps the preview links on. Each deploy of `main` sets **Preview URLs** from this line, whatever the dashboard says; with sensitive data it stays `false` until step 7 is done.
   - `[previews]` can stay empty, but must be there: Cloudflare's preview build needs it.
   - The two settings go near the top of the file, above its first line that starts with `[`, and `[previews]` goes at its end. A setting below a line in square brackets belongs to that block, so `[previews]` at the top would take in the settings below it. In a `wrangler.json` or `wrangler.jsonc` file, the same settings are `"workers_dev": false`, `"preview_urls": true` and `"previews": {}`.

7. **For a project with sensitive data** (phone numbers or payment details, say): Cloudflare Access on the preview links, or no previews. A preview link is public: anyone with it can open it. In your Worker's **Domains & Routes**, the **Preview URLs** row says "Anyone with this URL can visit", beside an **Enable Access** link. Click it, and allow only the people who should see previews, such as your own email address. Cloudflare may ask for a payment method to turn Access on, even on its free plan. Then tell Claude you have turned Access on, and ask it to change `preview_urls` to `true` in a pull request. The kit can't check Access itself: it relies on your word, which the "Add try-it links" upgrade (to come) records as `access = true` in your [profile](glossary.md#profile). Without Access, a project with sensitive data gets no previews: if you can't turn Access on, turn **Preview URLs** off in the dashboard (step 5) first, then keep `preview_urls = false` in the Wrangler config (ask Claude to change it back in a pull request if it says `true`): Cloudflare makes a public link for each branch while they are on.

**Then the kit:** your profile's [`[previews]`](profile.md#previews) section tells every session that previews are on (`on = true`). The "Add try-it links" upgrade (to come) adds that section in a pull request of its own, never by hand, and shows it working on that pull request's own link.

## When a build fails

Open the build's log from the **View logs** link in Cloudflare's comment on the pull request, or from the check's details. Then find what it says here:

| The build log says | What's wrong | The fix |
|---|---|---|
| "The name in your wrangler.toml file … must match the name of your Worker", though the names match | The Build command isn't empty, so the preview ran a deploy of the live site | Step 3: empty it on Production and Previews Base, then push a fresh branch |
| "Configured API token unavailable" | The build uses an old token | Step 4: **Create new token**, then push a new [commit](glossary.md#commit) to build again |
| "missing a `previews` block" | The Wrangler config has no `[previews]` | Step 6: add it in a pull request, then ask Claude to bring the failing pull request up to date with `main` |
| An error from `pip install .` | Your project has a `pyproject.toml`, so Cloudflare installs it as a Python package before building, and that failed | Ask Claude to fix what the error names, in a pull request |

If a build passes but no link arrives, preview URLs are off: step 5.

## What to expect

- **The link arrives by itself** on each pull request, as a comment from Cloudflare's bot and as a check named "Workers Builds:" and your Worker's name. The comment's **Branch Preview URL** is the try-it link, and always opens the branch's latest build. Each commit gets its own row in the comment's table.
- **The first build can take about four minutes to start.** Until the check for the latest commit is green, the link still shows the version before it.
- **A failed build** shows as a red check, and its row in the comment says the deployment failed: see "When a build fails".
- **Previews hold only made-up data.** Preview links are public unless step 7's Access guards them, so never put real people's details in a preview.
- **The try-it link's check is never a required one:** GitHub doesn't hold a merge for it. But once previews are on, the kit's merge check says "Not yet" while the link is still building, or when it didn't build.
