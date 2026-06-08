# Devvit app assets

Drop static assets referenced from `devvit.yaml` into this directory.

## App icon

To set an app icon (shown in the Devvit directory and in the app list on
subreddits where it's installed):

1. Save your icon as **`icon.png`** in this folder. Devvit expects:
   - **PNG** format
   - **256x256** pixels (square)
   - Reasonably small file size (under ~100 KB is fine)
2. Open `devvit/devvit.yaml` and uncomment the `icon:` line:
   ```yaml
   icon: assets/icon.png
   ```
3. From the `devvit/` directory, run:
   ```
   devvit upload
   ```
   The new icon will be bundled with the app. If the app has already
   been published, you may need to `devvit publish` again (or wait for
   the next review cycle) for the icon to appear in the public listing.
