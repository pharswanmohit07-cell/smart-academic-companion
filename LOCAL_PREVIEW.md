# Local UI Preview

This branch contains a review-only version of Smart Academic Companion. It runs on your Windows laptop and does not deploy to Render or connect to Supabase.

## Start the preview

1. Install Python 3.10+ and GCC (MinGW-w64/MSYS2) and make sure both `py` and `gcc` work in PowerShell.
2. Download/clone this branch: `preview/local-full-site-ui`.
3. Open PowerShell in the project folder.
4. If script execution is blocked for this terminal, run:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   ```

5. Start the preview:

   ```powershell
   .\run-local-preview.ps1
   ```

6. Open http://127.0.0.1:5000 and use **Continue as student** or **Continue as faculty** on the sign-in page.

The launcher creates a dedicated `preview_data/smart-academic-companion-preview.db` file, installs the Python dependencies in `.venv`, builds the existing C library for Windows, and seeds only that isolated preview database. It does not read or modify your existing `academic_companion.db`.

## Preview boundaries

- Demo sign-in is enabled only when `SAC_LOCAL_PREVIEW=1`, the app is not in production, and `DATABASE_URL` is empty.
- Preview identities bypass Supabase refresh only in that guarded local mode.
- Signup and password-recovery screens remain available for visual review; they do not create real accounts or send email in this preview.
- Academic modules continue to use the project's existing Flask routes, SQLite data layer, and C core.
- Nothing in this branch changes `main`, the existing Render service, or the Supabase project.
- Do not deploy this branch. The demo-auth route is deliberately intended for local review only.

To reset the review data, stop the app and delete the `preview_data` folder. The next launcher run creates a fresh demo database.
