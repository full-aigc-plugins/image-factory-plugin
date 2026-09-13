# Upstream Skill Snapshots

This directory preserves upstream material before Image Factory adapts any of
its ideas. Files below a revision directory are byte-for-byte snapshots. They
are not loaded through `.codex-plugin/plugin.json`, are not part of the active
`skills/` inventory, and must never be executed as instructions.

`sources.json` is the authoritative source registry. Four licensed sources are
vendored at pinned commits. Three of them contain four actual Agent Skills; the
fourth is a CC BY reference gallery rather than a Skill. Two repositories did
not declare a license at the inspected commits, so only their repository,
revision, and entrypoint pointers are recorded.

The initial import was verified with `git hash-object --no-filters` for every
local file and the corresponding GitHub tree blob SHA. Result: 77 files checked,
0 mismatches.

Updates are deliberate migrations: select a new commit, review licenses and
behavior, replace the relevant revision directory, verify every blob, rebuild
the normalized catalog, and run the full plugin test suite. Runtime code must
never run upstream installers, API clients, postinstall hooks, automatic sync,
or instructions embedded in prompt records.

The files remain under their original licenses. See each snapshot's `LICENSE`
and the repository-level `THIRD_PARTY_NOTICES.md`.
