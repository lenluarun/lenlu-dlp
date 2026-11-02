# Cloudflare hosting

## Cloudflare Pages

1. Create a Pages project from the repository.
2. Set the root directory to `landing`.
3. Leave the build command empty.
4. Set the output directory to `.`.
5. Deploy and use the generated Pages domain or a custom domain.

The landing page is static and can be served directly by Pages. Keep the local API and downloaded files on the user's machine; a static Cloudflare deployment cannot access `127.0.0.1` on a visitor's computer without the desktop app or a separately hosted backend.

## Installer downloads

Use GitHub Releases or Cloudflare R2 for `.exe` files. Link directly to the release asset instead of routing the binary through a Worker or Pages Function. This avoids function request and response limits and gives users a stable download URL.

For files below 25 MB, a direct static asset can work, but verify the current limits for the selected Cloudflare plan before publishing. The repository landing page already exposes both the current release and the legacy `V1.0.0` download.