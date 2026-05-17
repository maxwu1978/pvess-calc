# Deploying the docs site

The docs build via `mkdocs build` and deploy via GitHub Actions
(`.github/workflows/docs.yml`) using GitHub's official Pages deployment
flow — no `gh-pages` branch needed, no manual `mkdocs gh-deploy`.

## First-time setup (one engineer, once)

### 1. Update `mkdocs.yml` placeholders

Replace `your-org` and `pvess-calc` with your actual GitHub
org/repo names:

```bash
sed -i '' 's|your-org|MY_ORG|g; s|pvess-calc|MY_REPO|g' mkdocs.yml
```

Three lines change: `site_url`, `repo_url`, `edit_uri`.

### 2. Enable GitHub Pages

In the GitHub repo:

1. **Settings → Pages**
2. **Build and deployment → Source**: select **GitHub Actions**
   (NOT "Deploy from a branch")
3. Save

You can confirm by checking that the page shows
"Your site is ready to be published" — no further config needed.

### 3. Verify Actions permissions

In the same repo:

1. **Settings → Actions → General**
2. **Workflow permissions**: select
   **Read and write permissions** + tick
   **Allow GitHub Actions to create and approve pull requests**
3. Save

The `permissions:` block in `docs.yml` already requests
`pages: write` + `id-token: write` at the workflow level, but the
repo-wide setting must also allow it.

### 4. Trigger the first deploy

Either:

- Push any commit that touches `docs/`, `mkdocs.yml`, `README.md`, or
  the workflow file itself, OR
- Run the workflow manually: **Actions → Deploy docs to GitHub Pages
  → Run workflow → Run workflow on main**

After ~1 min, the docs go live at:

```
https://MY_ORG.github.io/MY_REPO/
```

Check the workflow's deploy step output — it prints the live URL.

## What triggers a deploy

The workflow runs on:

| Event | Behaviour |
|---|---|
| Push to `main` touching `docs/**`, `mkdocs.yml`, `README.md`, or the workflow file | **Builds + deploys** |
| Pull request touching the same paths | **Builds only** (catches docs regressions early; no deploy) |
| Manual via Actions tab | **Builds + deploys** (e.g. for hotfix or to verify after upstream theme update) |

Other commits (only `src/**` or `tests/**`) **don't** trigger the
workflow at all — saves CI minutes on non-docs work.

## Local preview before pushing

Always preview before pushing changes to `docs/`:

```bash
pip install -e ".[docs]"      # one-time
mkdocs serve                   # live-reload at http://127.0.0.1:8000
mkdocs build --strict          # one-shot strict build (catches broken links)
```

The CI uses `--strict` mode — any link or include that fails locally
will fail in Actions too.

## Troubleshooting

### "Get Pages site failed" in deploy step

Cause: GitHub Pages source is set to a branch (e.g. `gh-pages`) instead
of GitHub Actions.

Fix: **Settings → Pages → Source → GitHub Actions** (see step 2 above).

### "Resource not accessible by integration"

Cause: workflow permissions are too restrictive.

Fix: **Settings → Actions → General → Workflow permissions →
Read and write permissions** (see step 3 above).

### Site loads but assets 404

Cause: `site_url` in `mkdocs.yml` doesn't match the live URL — the
generated HTML still references the placeholder path.

Fix: update `site_url` to `https://MY_ORG.github.io/MY_REPO/`
(matching steps 1 + 4).

### Build passes locally, fails in CI with broken link

Cause: a `[link](relative/path)` resolves on macOS (case-insensitive FS)
but fails on Ubuntu (case-sensitive). Common with mismatched capitals
on file names.

Fix: rename to consistent case, e.g. `Workflow.md` → `workflow.md`.

## Internal deployment alternatives

If you can't use GitHub Pages (private repo / org policy):

- **`mkdocs gh-deploy`** — pushes built site to a `gh-pages` branch.
  Older flow; the workflow file would need a rewrite to use it.
- **Netlify / Cloudflare Pages** — build cmd `mkdocs build`, publish dir
  `site/`. Both can pull from a private GitHub repo.
- **Self-host** — copy `site/` to any static-file server.

For each of these, the docs source (Markdown under `docs/`) stays
identical — only the deployment plumbing differs.
