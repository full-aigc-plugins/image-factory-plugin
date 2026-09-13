# Prompt reference integration

This extension enriches preparation inside the existing four-Skill workflow.
The batch schema, generation adapter, approval policy and image receipts retain
their existing behavior. It does not add video rendering.

## Available now

- Offline search across 22 attributed structured templates.
- A 31-category gallery index for targeted case lookup.
- An 11-category prompt manifest for on-demand upstream browsing.
- Six pinned repository references with license and integration status.
- Chinese prompt adaptation, character consistency and storyboard guidance.

```bash
bin/image-factory prompt-search '成语绘本分镜' --limit 3 --json
```

The command performs no network request, writes no files and spends no image
allowance. Ranking is deterministic keyword matching with Chinese intent aliases,
not semantic retrieval or a quality score. Unknown queries return no template
matches and retain source links for manual discovery.

The source registry is in data/prompt-sources.json. MIT template metadata and
indexes are pinned and bundled with their complete licenses under licenses/.
The CC BY gallery is linked with its recorded license; two repositories with
unspecified licensing remain link-only. Community prompt text and preview
images are not bundled. Source counts are snapshot metadata, not tested results
or a claim that the complete galleries were imported.

The run Skill reads its prompt-preparation reference when a batch lacks a plan.
It chooses a template, optionally opens a relevant case, preserves attribution,
adapts the visual brief, and produces the existing validated batch format.
An already approved plan proceeds without unsolicited prompt rewriting.

## Validation and limits

Tests exercise Chinese search, no-match behavior, bounded output, source
provenance and invalid arguments through the real CLI. No new paid image
generation was performed for this extension. The effect on image quality remains
to be evaluated on future user batches.

Skill review covered Trust (attribution and untrusted-source handling),
Reliability (offline fallback), Adaptability (Chinese intents and supplied plans),
Convention (progressive reference loading) and Effectiveness (real CLI search).
No numerical TRACE score or perfect-quality certification is claimed.
