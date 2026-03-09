# Forma Blog Automation

Automated blog post generation and publishing for [blog.formafit.co.uk](https://blog.formafit.co.uk).

---

## How It Works

```
Every 2 weeks (Monday 08:00 UTC)
        ↓
GitHub Actions runs forma_blog_scheduler.py
        ↓
  1. Picks next category from rotation (HRV → Recovery → Wearables → Race Prep → repeat)
  2. Reads existing posts so AI never repeats a topic
  3. Calls Anthropic API → generates full SEO-optimised post
  4. Commits to draft/post-YYYY-MM-DD branch
  5. Opens Pull Request on GitHub
        ↓
You receive email: "New blog post ready for review"
  → Click PR link → read the post (in posts_manifest.json diff)
  → Happy? Click MERGE → post goes live in ~60 seconds
  → Changes needed? Edit posts_manifest.json on the branch, or comment
```

---

## Files

| File | Purpose |
|---|---|
| `forma_blog_scheduler.py` | Generates posts + creates draft PRs |
| `forma_blog_publish.py` | Clears draft status on PR merge |
| `forma_blog_build.py` | Builds all HTML from manifest (run by Netlify) |
| `posts_manifest.json` | Source of truth — all post data + HTML |
| `content_calendar.json` | Category rotation, tone guidelines, history |
| `forma_fonts.css` | Embedded Oxanium font (all 7 weights) |
| `.github/workflows/blog-scheduler.yml` | Cron trigger (every 2 weeks) |
| `.github/workflows/blog-publish.yml` | Publish trigger (on PR merge) |

---

## Setup (one-time)

### 1. Add ANTHROPIC_API_KEY secret
GitHub → repo → Settings → Secrets and variables → Actions → New secret:
- Name: `ANTHROPIC_API_KEY`
- Value: your key from platform.anthropic.com

### 2. Enable GitHub Actions write permissions
GitHub → repo → Settings → Actions → General → Workflow permissions:
- Select **"Read and write permissions"**
- Check **"Allow GitHub Actions to create and approve pull requests"**

### 3. Confirm Netlify build settings
- Build command: `pip install -r requirements.txt && python forma_blog_build.py`
- Publish directory: `output`
- Branch: `main`

That's it. The first post generates automatically on the next scheduled Monday.

---

## Manual Trigger

To generate a post immediately (without waiting for the schedule):

GitHub → Actions → "Forma Blog Scheduler" → "Run workflow" → Run

---

## Changing the Schedule

Edit `.github/workflows/blog-scheduler.yml`:
```yaml
schedule:
  - cron: '0 8 * * 1/14'  # Every 2 weeks, Monday 08:00 UTC
```

Cron syntax: minute hour day-of-month month day-of-week
- Every week: `0 8 * * 1`
- Every 2 weeks: `0 8 * * 1/14` *(note: GitHub doesn't support /14 reliably — use manual trigger or a 14-day counter)*

---

## Adding or Changing Categories

Edit `content_calendar.json` → `category_rotation` array.
Add, remove, or reorder categories. The `next_category_index` tracks where the rotation is.

---

## Reviewing a Draft Post

When you get the PR email:
1. Click the PR link
2. Go to "Files changed" tab
3. Find `posts_manifest.json` — the new post's `body_html` is the article content
4. Or: copy the slug, go to `blog.formafit.co.uk/blog/SLUG.html` (won't exist yet — it's draft)

To preview locally before merging:
```bash
git fetch origin
git checkout draft/post-YYYY-MM-DD-slug
python forma_blog_build.py
open output/blog/SLUG.html
```

---

## Category Rotation

| Position | Category | Description |
|---|---|---|
| 1 | Training Science / HRV | HRV, periodisation, VO2 max, training zones |
| 2 | Recovery & Sleep | Sleep quality, overtraining, deload weeks |
| 3 | Wearables & Data | Garmin, Oura, WHOOP comparisons |
| 4 | Race Prep & Performance | Tapering, race day, marathon/cycling prep |

---

## Generation History

Tracked automatically in `content_calendar.json` → `generation_history`.
