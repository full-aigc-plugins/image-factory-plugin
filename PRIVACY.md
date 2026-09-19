# Privacy

Image Factory is a local, cross-host plugin. It does not include telemetry, advertising, or a hosted data service, and it does not ship credentials.

The plugin reads a batch plan and any reference images you explicitly name, and it collects generated images from the active host's artifact directory. Batch plans, ledgers, receipts, and scores are written under the job directory you select. Nothing in this repository transmits files or prompts to a service operated by this project.

Image generation is performed by the active host using its image tool and your existing host authentication. Prompts and reference images therefore leave your machine as part of that generation call, under the terms of the account you are already using. The plugin never reads, copies, or stores your authentication material; the host handles its own credentials.

Users should review the privacy terms of any connected product before enabling an integration.
