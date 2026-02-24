# Architecture

NBKP is an rsync-based backup tool. The execution flow is:

```
CLI (cli.py) → Runner (runner.py) → Check (check.py) + Rsync (rsync.py) + Btrfs (btrfs.py)
                                         ↓                    ↓                    ↓
                                    SSH (ssh.py)          SSH (ssh.py)         SSH (ssh.py)

```

All modules resolve volumes from `Config.volumes[name]` and dispatch on volume type.

## Key dispatch pattern

`LocalVolume | RemoteVolume` (the `Volume` union type) is used throughout. Every module that touches the filesystem branches on `isinstance(vol, RemoteVolume)` — local operations use `pathlib`/`subprocess` directly, remote operations go through `ssh.run_remote_command()`.


## Sync flow (runner.py)

1. `check_all_syncs()` — verifies volumes are reachable and marker files exist (`.nbkp-vol`, `.nbkp-src`, `.nbkp-dst`)
2. For each active sync: get latest btrfs snapshot (if enabled) → `run_rsync()` with optional `--link-dest` → `create_snapshot()` (if btrfs enabled and not dry run)
3. rsync always writes to `{destination}/latest/`; snapshots go to `{destination}/snapshots/{ISO8601Z}`

## Rsync command variants (rsync.py)

- **Local→Local**: direct rsync
- **Local→Remote / Remote→Local**: rsync with `-e "ssh -p PORT -i KEY -o OPT"`
- **Remote→Remote**: SSH into destination, run rsync from there pointing at source

## Config resolution (config.py)

Search order: explicit path → `$XDG_CONFIG_HOME/nbkp/config.yaml` → `/etc/nbkp/config.yaml`. Raises `ConfigError` on validation failure.
