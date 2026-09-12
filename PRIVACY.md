# Privacy

Codex Image Factory is a local Codex plugin. It does not include telemetry, advertising, or a hosted data service, and it does not ship credentials.

The plugin reads a batch plan and any reference images you explicitly name, and it collects generated images from your local Codex home directory. Batch plans, ledgers, receipts, and scores are written under the job directory you select. Nothing in this repository transmits files or prompts to a service operated by this project.

Image generation is performed by Codex itself using the built-in image tool and your own Codex authentication. Prompts and reference images therefore leave your machine as part of that generation call, under the terms of the account you are already using. The plugin never reads, copies, or stores your authentication material; it invokes Codex and lets Codex handle its own credentials.

Users should review the privacy terms of any connected product before enabling an integration.
