# OpenClaw Discord Lifecycle State

Small Python helpers for recording and reading lifecycle state for Discord-backed
OpenClaw project channels.

The package keeps storage separate from display projections:

- mapped project channels use a project-local `LIFECYCLE_STATE.md`;
- unmapped channels use a channel-local JSON registry keyed by Discord channel
  id;
- Discord display changes are explicit dry-run/apply operations, not side
  effects of state writes.

## Status

This is an early public split of code extracted from a private project-management
repository. It is suitable for review and experimentation, but the API should be
treated as pre-1.0.

## Development

```bash
PYTHONPATH=src python -m pytest tests -q
```

## License

MIT.
