# Demo Assets

This folder contains the current demo screenshots used for the public alpha docs.

It also holds generated terminal demo recordings when available, including:

- `proof-of-audit-agent-demo.cast`

Generated screenshots:

- `workbench-overview.png`
- `workbench-draft-claim.png`
- `workbench-deterministic-resolution.png`

Refresh them with:

```bash
cd /home/koita/dev/hackatons/proof-of-audit
zsh -lic './scripts/capture-demo-assets.sh'
```

The capture flow boots the local demo stack, opens the workbench, and records the main deterministic resolution path.
