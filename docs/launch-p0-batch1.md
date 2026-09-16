# Launch P0 Batch 1

## Frozen baseline

```text
Release baseline branch: codex/beta-release
Release baseline commit: 0be8729b92693d3eed19c41de31a271c1cf7026a
Implementation branch: codex/launch-p0-batch1
```

The release baseline remains unchanged. Batch 1 work must be reviewed and pass
the complete regression and security gates before it can replace that baseline.

## In scope

- Redis-backed login, registration, upload, and AI abuse controls.
- Per-provider-call AI charging, including streaming and JSON repair.
- User, IP, device, global daily, global concurrency, and kill-switch controls.
- Registration rate limiting and concurrent uniqueness handling.
- PDF page/text limits, Excel row/column limits, XLSX decompression limits,
  bounded off-event-loop parsing, parser timeouts, and upload rate limiting.
- Server-authoritative sandbox resume.
- Automated regression and adversarial tests for the changes above.

## Not in scope

- Public HTTPS, reverse proxy, DNS, ICP filing, and WeChat legal domains.
- Account-deletion checkpoint cleanup and JWT revocation.
- Production backup and restore.
- New Study features, new Agents, or new product pages.

Those remaining launch gates keep the repository at `NO-GO` even after Batch 1
passes. No real-user traffic is authorized by this branch alone.
