# Deploying the app (Streamlit Community Cloud)

The app runs from `code/streamlit_app.py`. On Streamlit Community Cloud it detects that it is shared and keeps every
visitor's uploaded files private to their browser session (temporary folder, deleted after a few hours).
On a laptop, entered dates persist in `input_data/uploaded/` instead. To force either mode, set the environment
variable `ZCYC_MULTIUSER` to `1` (shared) or `0` (single user).

## Before you start
* **FBIL data.** `input_data/` contains FBIL's files. Publish them only if FBIL's terms allow it; otherwise use a **private**
  GitHub repository (visitors then upload their own files, which the app already supports).
* You need a free GitHub account and a free Streamlit Community Cloud account (sign in there with GitHub).

## 1. Put the project on GitHub
The repository root must be the project folder, the one that contains `code/`, `input_data/` and `additional_material/`.

1. On github.com choose New repository, name it (for example `zcyc-app`), choose Private, and create it empty.
2. In a terminal, from inside the project folder:
   ```
   git init
   git add .
   git commit -m "ZCYC app"
   git branch -M main
   git remote add origin https://github.com/<your-username>/zcyc-app.git
   git push -u origin main
   ```
   (Or use GitHub Desktop: File > Add local repository, then Publish repository. The GitHub website's drag-and-drop upload is
   limited to 100 files, so it is not suitable.)

## 2. Create the app
1. Go to https://share.streamlit.io and sign in with GitHub.
2. Choose Create app > "Yes, I have an app", and select your repository.
3. Branch: `main`. Main file path: `code/streamlit_app.py`.
4. Open Advanced settings and choose Python 3.12. No secrets are needed.
5. Choose Deploy. The first build takes a few minutes; you get a link like `https://<name>.streamlit.app`.

## 3. Check it
Open the link and confirm: the 11 Sep results show 6.38 bp (exact fit) and 1.75 bp (smoothed fit); the STRIPS tab shows the
2058 SDL with factor 0.97963; entering a date works and its files are not visible from a second browser.

## Notes
* Free apps go to sleep after a period without visitors and wake on the next visit.
* To update the app, push to the same branch; it redeploys automatically.
* If the build fails, the log in the app's Manage menu names the missing package; `requirements.txt` in the repository root
  (a copy of `code/requirements.txt`) is what the build installs.
