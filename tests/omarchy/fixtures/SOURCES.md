# Omarchy fixtures (verbatim upstream copies)

Copied from the source app (`tests/omarchy/fixtures/` at 39b6acc), unchanged. Used only by `tests/omarchy/run.sh`,
`tests/dry_run.sh` and `tests/model.test.mjs` to build a mocked Omarchy tree. Omarchy is MIT licensed,
Copyright (c) David Heinemeier Hansson; see THIRD_PARTY_NOTICES.md.

## `v4/` (basecamp/omarchy quattro branch at 8a787b6a8bec830b04543bf14c760ee0a10591f6)
| file | source (raw) | sha256 |
|---|---|---|
| `v4/bin/omarchy-toggle-enabled` | https://raw.githubusercontent.com/basecamp/omarchy/8a787b6a8bec830b04543bf14c760ee0a10591f6/bin/omarchy-toggle-enabled | `5f5b2797e2f5912f…` |
| `v4/themes/tokyo-night/colors.toml` | https://raw.githubusercontent.com/basecamp/omarchy/8a787b6a8bec830b04543bf14c760ee0a10591f6/themes/tokyo-night/colors.toml | `8b5f53ba35b9305a…` |

## Added 2026-10-17 (lock on wake): `v4-real/`, copied read-only from Michael's XPS (Omarchy 4.0.0.alpha)
Copied 2026-10-17 from `fixtures/omarchy-real/` (the tarball `fixtures/omarchy-real-4.0.0.alpha.tgz`, read-only copies from
the XPS), unchanged. Byte-identical to basecamp/omarchy tag v4.0.4 (c668141) per the planner's comparison
(reports/plan-fix1.md 1.2). The idle `Service.qml` here differs from `v4/` (quattro is newer); the lock tests use this one.
`tests/omarchy/run.sh` section 25q checks every sha256 below (full values) and `cmp`s against `fixtures/omarchy-real/` when it exists.

| file | sha256 |
|---|---|
| `v4-real/bin/omarchy-hyprland-session-locked` | `e5004580e41475932f852d622b36ec07bfb0e98633c4d3c3055071a54d0eda07` |
| `v4-real/bin/omarchy-launch-screensaver` | `b58b82a6b9edc901c83da50a3e2b2ac7fee8d1311a7f327a9ec8901ff8028338` |
| `v4-real/bin/omarchy-screensaver` | `9ad1b57d322b5ed04112824ef48c98b7f14f1f08a60b583395558afbfd9fb7d2` |
| `v4-real/bin/omarchy-system-lock` | `f1953110658d819597d3c9d8df616350c362ee4c257227fcbdefac8275bbd596` |
| `v4-real/bin/omarchy-system-sleep-lock` | `6081b11c89d47ab3242a5eb25793724ebd09e1a99aa391950fea6e08b559cb39` |
| `v4-real/config/omarchy/shell.json` | `b16dc9646bf68e81643522cef504795d97cb5016d80d8b65784bde44f2c0883f` |
| `v4-real/shell/plugins/lock/Service.qml` | `3f0a265a09f7957e8f5d74666595d3136ec64899c414426190460f9e2098e701` |
| `v4-real/shell/plugins/services/idle/IdleModel.js` | `58226a67d5fc2f33b1a23b55cb32764a8b2091cc94c4d02af1b67f369440b9b8` |
| `v4-real/shell/plugins/services/idle/Service.qml` | `50f5c81e2e94fab32395a5bc3cce982e30a10ab1b3f56cc58f29055951518a51` |
| `v4-real/shell/plugins/services/idle/manifest.json` | `bb8a5f55257dc49c2b7632304dad19aa12bbc7ad641828f09481909232f30a6f` |
| `v4-real/version` | `9d1aaeb0c16104d678742c04d6a8700fed365e7eb65a8eaef5fb3845ddf634e3` |
