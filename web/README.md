# Change UI development

The editable UI lives here. Kajamite ships the compiled HTML and license notices.
Python package users need neither Node nor a frontend build.

## Build

Use Node 22.23.2 and npm 10.9.8 for the release build:

```sh
npm ci --ignore-scripts
npm run build
npm run check
```

`build.mjs` bundles production React and selected shadcn controls with esbuild.
Tailwind compiles the semantic utility classes. The output has inline JavaScript
and CSS, with no external fonts, CDN imports, or runtime asset requests.

Commit source changes, `package-lock.json`, and the generated files:

- `src/kajamite/knowledge-change.html`
- `src/kajamite/UI-NOTICES.txt`
- `src/kajamite/ui-build.json`

Run `python tools/check_ui.py` from the repository root. The Python build hook
checks the source and output hashes for both wheel and source distributions.
Stale artifacts fail with a rebuild instruction. The hook never invokes npm.
CI also rebuilds the UI to check reproducibility and runs browser acceptance.

## Components and guidance

The UI composes shadcn Button, Card, Collapsible, and Separator source.
Source was selected from the official new-york-v4 registry on 2026-09-14.
Imports use individual Radix packages and the local `cn` helper.
The shadcn MIT license is in `SHADCN-LICENSE.txt`; the build collects licenses
for all bundled JavaScript packages into the Python distribution.

Use the [shadcn agent guidance](https://github.com/shadcn-ui/ui/blob/main/skills/shadcn/SKILL.md).
Inspect project context with `npx shadcn@latest info --json` and component
references with `npx shadcn@latest docs button card collapsible separator`.
Review CLI changes before adding dependencies, and pin accepted versions.
Prefer semantic tokens, built-in variants, composition, and layout-only overrides.

The card and expanded detail share a source-faithful comparison surface. Large
regions reveal locally through one seam, with a gutter fold control after
expansion. Inline comparison scrolls within a bounded region; expanded detail
uses the page scroll and offers unified/split layouts. Raw evidence remains
behind an optional disclosure. Host display refusal retains local expansion.

## Adopter themes

See [UI theming](../docs/ui-theming.md). Adopters configure exported theme tokens;
they do not edit these sources or run a build. Theme-file changes apply after
server restart and loading a new result. Host light/dark notifications update
an open result. Theme tokens cannot load fonts or other external assets.
