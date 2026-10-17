# Cloudflare Workers Builds fixtures (#113)

Made-up GitHub data in the shape of a pull request with Cloudflare's Workers Builds integration, for `tests/test_preview.py`. Nothing here was recorded: the names (`acme/demo`, the `demo-notes` Worker, `example-account`), SHAs, ids and URLs are invented.

Two moments of one pull request, each as `<moment>.comments.json` (the PR's issue comments, as `GET repos/<repo>/issues/<n>/comments` returns them), `<moment>.check-runs.json` (the head commit's check runs, as `GET repos/<repo>/commits/<sha>/check-runs` returns them) and `<moment>.sha` (the head commit):

- `failed`: the first push; the build failed.
- `built`: a later push; the build succeeded. The bot edited the same comment (same id, later `updated_at`).

The shape follows Cloudflare's public documentation, as of October 2026:

- [GitHub integration](https://developers.cloudflare.com/workers/ci-cd/builds/git-integration/github-integration/): the bot (`cloudflare-workers-and-pages`) comments on the pull request and edits that one comment for later builds; its screenshot shows the "Deploying with Cloudflare Workers" heading, the line "The latest updates on your project…", and a table with the columns Status, Name, Latest Commit, Preview URL and Updated (UTC), the status "✅ Deployment successful!" with "View logs", and the links "Commit Preview URL" and "Branch Preview URL". Its check runs are named `Workers Builds: <worker>`, from the Cloudflare Workers and Pages GitHub App (slug `cloudflare-workers-and-pages`).
- [Previews](https://developers.cloudflare.com/workers/previews/): a Preview URL (`<preview-name>-<worker-name>.<subdomain>.workers.dev`, always the branch's latest) and a Deployment URL (`<deployment-id>-<worker-name>.<subdomain>.workers.dev`).

Assumed, since the documentation shows only the rendered comment:

- the comment's Markdown: a pipe table, the commit as a code-styled link to the commit, links in Markdown, `<br>` between them;
- a failed build's status, "❌ Deployment failed", with an empty Preview URL cell;
- the check run's fields beyond its name and app (`details_url` to the build's logs, an empty `output`).

Checking the reader against a real recording (the sandbox's trial PR) is a by-hand check on the run's by-hand issue (#173).
