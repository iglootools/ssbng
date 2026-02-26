# Architecture

NBKP is an rsync-based backup tool. The execution flow is:

```
CLI (cli.py) → Runner (runner.py) → Check (check.py) + Rsync (rsync.py) + Btrfs (btrfs.py) + Hardlinks (hardlinks.py)
                                         ↓                    ↓                    ↓                    ↓
                                    SSH (ssh.py)          SSH (ssh.py)         SSH (ssh.py)         SSH (ssh.py)

```

All modules resolve volumes from `Config.volumes[name]` and dispatch on volume type.

## Key dispatch pattern

`LocalVolume | RemoteVolume` (the `Volume` union type) is used throughout. Every module that touches the filesystem branches on `isinstance(vol, RemoteVolume)` — local operations use `pathlib`/`subprocess` directly, remote operations go through `ssh.run_remote_command()`.


## Sync flow (runner.py)

1. `check_all_syncs()` — verifies volumes are reachable and marker files exist (`.nbkp-vol`, `.nbkp-src`, `.nbkp-dst`)
2. For each active sync, dispatch on `snapshot_mode`:
   - **`none`**: `run_rsync()` → done
   - **`btrfs`**: `run_rsync()` to `{destination}/latest/` → `create_snapshot()` → optional `prune_snapshots()`
   - **`hard-link`**: cleanup orphans → resolve `--link-dest` from previous snapshot → `create_snapshot_dir()` → `run_rsync()` to `{destination}/snapshots/{timestamp}/` → `update_latest_symlink()` → optional `prune_snapshots()`
3. Btrfs syncs write to `{destination}/latest/`; hard-link syncs write directly to `{destination}/snapshots/{ISO8601Z}/`. Both store snapshots under `{destination}/snapshots/`.

## Rsync command variants (rsync.py)

- **Local→Local**: direct rsync
- **Local→Remote / Remote→Local**: rsync with `-e "ssh -p PORT -i KEY -o OPT"`
- **Remote→Remote (different servers)**: SSH into source, run rsync pushing to destination via `-e "ssh ..."`
- **Remote→Remote (same server)**: SSH into the server once, run rsync with local paths

## Config resolution (config.py)

Search order: explicit path → `$XDG_CONFIG_HOME/nbkp/config.yaml` → `/etc/nbkp/config.yaml`. Raises `ConfigError` on validation failure.
