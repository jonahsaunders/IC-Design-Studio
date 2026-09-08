# Upload IC Design Studio to GitHub

Extract `IC-Design-Studio-0.13.0-GitHub-Ready.zip`. The `IC-Design-Studio` folder is the repository root: it contains `README.md`, `main.py`, `icstudio/` and `.github/`. Upload the extracted files so GitHub can display the source and run the workflow.

## Git commands

1. Sign in at [GitHub](https://github.com/new) and create an empty repository named `IC-Design-Studio`. Choose your preferred visibility. Leave the README, license and .gitignore initialization options off; these files are already included.
2. Open a terminal inside the extracted `IC-Design-Studio` folder. Run:

```sh
git init -b main
git add .
git update-index --chmod=+x launch-linux.sh
git status --short
git commit -m "Import IC Design Studio 0.13.0"
git remote add origin https://github.com/YOUR-USERNAME/IC-Design-Studio.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your GitHub user or organization name. Authenticate with your configured Git credential manager, GitHub CLI or SSH setup when prompted. If Git requests an author identity, configure your own name and email before committing. These commands target a new, empty repository.

The ZIP contains a source snapshot, without prior Git history or a preconfigured remote.

## GitHub Desktop

As a graphical alternative, initialize the folder with `git init -b main`, then use **File → Add local repository** in GitHub Desktop and select that folder. Review and commit the files, then select **Publish repository**, choose visibility and publish. If you already created the empty repository on GitHub, clone it in Desktop and copy the extracted project contents into the clone before committing and pushing.

## Browser upload

The GitHub browser uploader accepts up to 100 files per upload and 25 MiB per file. This project exceeds 100 files in total, so upload in batches. Each top-level source directory fits within one batch.

From the repository root on GitHub, use **Add file → Upload files** and drag one extracted directory at a time (`icstudio`, `docs`, `tests`, `licenses`, and so on), committing each batch. Add the root files in another batch. Preserve the directory names, and include `.github`, `.gitignore` and `.gitattributes`; enable hidden-file display in your file manager if necessary. Do not drag the outer `IC-Design-Studio` folder into an existing repository, which would nest the entire app one level too deep. Git or Desktop is the simpler route for transferring every file together.

## Optional release downloads

After pushing the source, you can create a GitHub Release tagged `v0.13.0`. Mark the engineering preview as a pre-release. Use `docs/UPDATE_0.13.md` for the release notes and retain the platform qualification limits.

The original handoff ZIP contains these companion files under `release/`:

| Original file | Use |
| --- | --- |
| `IC-Design-Studio-0.13.0-Linux-x86_64.tar.gz` | Prebuilt Linux engineering preview; attach to the Release |
| `IC-Design-Studio-0.13.0-Source.zip` | Original corresponding source for the supplied Linux binary |
| `IC-Design-Studio-0.13.0-Evidence-and-Examples.zip` | Current examples and validation evidence |
| `IC-Design-Studio-0.8.0-PDKs-and-Evidence.zip` | Unchanged companion PDK package and historical evidence |
| `IC-Design-Studio-0.13.0-Update.md` | Original update guide |
| `SHA256SUMS-0.13.0.txt` | Checksums for those original release files |

The original 117 MB Linux archive exceeds GitHub's 100 MiB Git file limit. Keep these companion downloads out of the Git source tree; the repository's `.gitignore` excludes release archives and build outputs. Their bytes and checksums remain those of the original handoff. The original checksum file does not describe this prepared repository ZIP.

To generate fresh source archives from this repository, use `python scripts/release_archives.py --output release`. A rebuilt binary needs newly generated matching source and checksums. The existing Actions workflow produces build artifacts and does not automatically create releases.

See [REPOSITORY_PREPARATION.md](docs/REPOSITORY_PREPARATION.md) for the changes and local validation results.

## After upload

- Check that `README.md` and `main.py` appear at the repository root.
- Open **Actions → Build and verify desktop release** to inspect the initial build. The workflow also supports manual **Run workflow**.
- Linux and Windows jobs must actually finish successfully before their output can be described as tested. Fresh desktop and human acceptance remain separate checks.
- Keep GPL licensing and third-party notices with distributed source and app bundles.

Official GitHub instructions:

- [Adding locally hosted code](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)
- [Uploading files in the browser](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)
- [Large files and release distribution](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
