# Deploy the Kuwait pricing fix on Render

The YesStyle scraper uses Chromium to select Kuwait, USD, and English,
reload the product, and verify the displayed regional selling price.
It does not fall back to another destination's price if verification fails.

For the existing **Python** web service, set:

- Branch: `main`
- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt && python -m playwright install chromium`
- Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Environment variable: `PLAYWRIGHT_BROWSERS_PATH=0` (used at both build and runtime)
- Keep the existing `GROQ_API_KEY` environment variable.

Do not create a second service or change the frontend API URL.
After saving the settings, use **Manual Deploy > Deploy latest commit**.
If auto-deploy is On Commit, pushes to main also trigger a deployment.

If browser startup reports missing Linux shared libraries, the native runtime
needs additional system dependencies. Use a Docker runtime with Playwright's
documented browser dependencies rather than ignoring that error. Capture the
exact build/startup error before changing the deployment strategy.

After Render reports Live, analyze product `1126934079` in the frontend and
enter its known shipping weight. Compare its USD price against YesStyle with
shipping destination Kuwait and currency USD. The observed price during
development was US$10.71; this is not hardcoded and can change with promotions.

Offline regression checks: `python -m unittest discover -s backend -p 'test_*.py'`
(run from the repository root after installing backend requirements).

Browser requests are serialized within each backend process to limit memory.
Render's free instance still needs to be tested for browser memory usage and
YesStyle access after deployment. `/api/health` checks the API only, not browser
availability or regional scraping.
