"""Generate a standalone bash script from nbkp config.

Compiles a Config into a self-contained shell script that performs
the same sync operations as ``nbkp run``, with all paths and
options baked in.  The generated script accepts ``--dry-run``
and ``--verbose`` flags at runtime.
"""

from __future__ import annotations

import importlib.resources
import os
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from textwrap import dedent

from jinja2 import Environment, Template

from .config import (
    Config,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
)
from .remote.ssh import build_ssh_base_args
from .sync.rsync import build_rsync_command

# ── Public API ────────────────────────────────────────────────


@dataclass(frozen=True)
class ScriptOptions:
    """Options for script generation."""

    config_path: str | None = None
    output_file: str | None = None
    relative_src: bool = False
    relative_dst: bool = False


def generate_script(
    config: Config,
    options: ScriptOptions,
    *,
    now: datetime | None = None,
) -> str:
    """Generate a standalone bash script from config."""
    if now is None:
        now = datetime.now(timezone.utc)
    vol_paths = _build_vol_paths(config, options)
    ctx = _build_script_context(config, options, vol_paths, now)
    template = _load_template()
    return template.render(ctx) + "\n"


# ── Context dataclasses ──────────────────────────────────────


@dataclass(frozen=True)
class _SyncContext:
    slug: str
    fn_name: str
    enabled: bool
    has_btrfs: bool = False
    has_prune: bool = False
    max_snapshots: int | None = None
    preflight: str = ""
    link_dest: str = ""
    rsync: str = ""
    snapshot: str = ""
    prune: str = ""
    disabled_body: str = ""


# ── Template loading ─────────────────────────────────────────


def _load_template() -> Template:
    """Load the Jinja2 template with custom delimiters."""
    tpl_text = (
        importlib.resources.files("nbkp.templates")
        .joinpath("backup.sh.j2")
        .read_text(encoding="utf-8")
    )
    env = Environment(
        variable_start_string="${{",
        variable_end_string="}}",
        block_start_string="<%",
        block_end_string="%>",
        comment_start_string="<#",
        comment_end_string="#>",
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env.from_string(tpl_text)


# ── Path helpers ─────────────────────────────────────────────


def _build_vol_paths(
    config: Config,
    options: ScriptOptions,
) -> dict[str, str]:
    """Compute volume slug -> effective path."""
    src_slugs = {s.source.volume for s in config.syncs.values()}
    dst_slugs = {s.destination.volume for s in config.syncs.values()}

    vol_paths: dict[str, str] = {}
    for slug, vol in config.volumes.items():
        match vol:
            case RemoteVolume():
                vol_paths[slug] = vol.path
            case LocalVolume():
                should_relativize = (
                    slug in src_slugs and options.relative_src
                ) or (slug in dst_slugs and options.relative_dst)
                if should_relativize and options.output_file:
                    output_dir = os.path.dirname(options.output_file)
                    rel = os.path.relpath(vol.path, output_dir)
                    vol_paths[slug] = f"${{NBKP_SCRIPT_DIR}}/{rel}"
                else:
                    vol_paths[slug] = vol.path
    return vol_paths


def _vol_path(
    vol_paths: dict[str, str],
    slug: str,
    subdir: str | None = None,
) -> str:
    base = vol_paths[slug]
    if subdir:
        return f"{base}/{subdir}"
    return base


def _substitute_vol_path(
    arg: str,
    vol: LocalVolume | RemoteVolume,
    vol_paths: dict[str, str],
    slug: str,
) -> str:
    """Replace absolute volume path prefix with vol_paths."""
    match vol:
        case RemoteVolume():
            return arg
        case LocalVolume():
            return arg.replace(vol.path, vol_paths[slug], 1)


# ── Shell formatting helpers ─────────────────────────────────


def _sq(s: str) -> str:
    """Shell-quote (single quotes, no variable expansion)."""
    return shlex.quote(s)


def _qp(s: str) -> str:
    """Quote a path; double-quote if it contains $."""
    if "$" not in s:
        return _sq(s)
    return f'"{s}"'


def _slug_to_fn(slug: str) -> str:
    return f"sync_{slug.replace('-', '_')}"


def _format_shell_command(
    cmd: list[str],
    cont_indent: str = "        ",
) -> str:
    """Format command list with backslash continuations."""
    parts = [_qp(arg) for arg in cmd]
    if len(parts) <= 3:
        return " ".join(parts)
    sep = f" \\\n{cont_indent}"
    return parts[0] + sep + sep.join(parts[1:])


# ── SSH command helpers ──────────────────────────────────────


def _format_remote_test(
    server: RsyncServer,
    proxy: RsyncServer | None,
    test_args: list[str],
) -> str:
    ssh_args = build_ssh_base_args(server, proxy)
    remote_cmd = "test " + " ".join(shlex.quote(a) for a in test_args)
    return " ".join(_sq(a) for a in ssh_args) + " " + _sq(remote_cmd)


def _format_remote_check(
    server: RsyncServer,
    proxy: RsyncServer | None,
    cmd: list[str],
) -> str:
    ssh_args = build_ssh_base_args(server, proxy)
    remote_cmd = " ".join(shlex.quote(a) for a in cmd)
    return (
        " ".join(_sq(a) for a in ssh_args)
        + " "
        + _sq(remote_cmd)
        + " >/dev/null 2>&1"
    )


def _format_remote_command_str(
    server: RsyncServer,
    proxy: RsyncServer | None,
    cmd: list[str],
) -> str:
    ssh_args = build_ssh_base_args(server, proxy)
    remote_cmd = " ".join(shlex.quote(a) for a in cmd)
    return " ".join(_sq(a) for a in ssh_args) + " " + _sq(remote_cmd)


# ── Local/remote dispatch helpers ────────────────────────────


def _test_cmd(
    vol: LocalVolume | RemoteVolume,
    config: Config,
    test_args: list[str],
) -> str:
    """Shell expression for `test ... `."""
    match vol:
        case LocalVolume():
            return "test " + " ".join(_qp(a) for a in test_args)
        case RemoteVolume():
            server = config.rsync_servers[vol.rsync_server]
            proxy = config.resolve_proxy(server)
            return _format_remote_test(server, proxy, test_args)


def _which_cmd(
    vol: LocalVolume | RemoteVolume,
    config: Config,
    command: str,
) -> str:
    """Shell expression to check command availability."""
    match vol:
        case LocalVolume():
            return f"command -v {_sq(command)} >/dev/null 2>&1"
        case RemoteVolume():
            server = config.rsync_servers[vol.rsync_server]
            proxy = config.resolve_proxy(server)
            return _format_remote_check(server, proxy, ["which", command])


def _ls_snapshots_cmd(
    dst_vol: LocalVolume | RemoteVolume,
    config: Config,
    snaps_dir: str,
) -> str:
    """Shell expression to list snapshot dirs."""
    match dst_vol:
        case LocalVolume():
            return f"ls {_qp(snaps_dir)}"
        case RemoteVolume():
            server = config.rsync_servers[dst_vol.rsync_server]
            proxy = config.resolve_proxy(server)
            return _format_remote_command_str(server, proxy, ["ls", snaps_dir])


def _snapshot_cmd(
    dst_vol: LocalVolume | RemoteVolume,
    config: Config,
    latest: str,
    snaps_dir: str,
) -> str:
    """Shell command to create a btrfs snapshot."""
    snap_args = [
        "btrfs",
        "subvolume",
        "snapshot",
        "-r",
        latest,
        f"{snaps_dir}/$NBKP_TS",
    ]
    match dst_vol:
        case LocalVolume():
            return _format_shell_command(snap_args, cont_indent="        ")
        case RemoteVolume():
            server = config.rsync_servers[dst_vol.rsync_server]
            proxy = config.resolve_proxy(server)
            remote_args = [
                "btrfs",
                "subvolume",
                "snapshot",
                "-r",
                latest,
                f"{snaps_dir}/\\$NBKP_TS",
            ]
            return _format_remote_command_str(server, proxy, remote_args)


def _btrfs_prop_cmd(
    dst_vol: LocalVolume | RemoteVolume,
    config: Config,
    snaps_dir: str,
) -> str:
    """Shell command to set ro=false on $snap."""
    match dst_vol:
        case LocalVolume():
            return (
                f"btrfs property set" f' {_qp(snaps_dir)}/"$snap"' f" ro false"
            )
        case RemoteVolume():
            server = config.rsync_servers[dst_vol.rsync_server]
            proxy = config.resolve_proxy(server)
            return _format_remote_command_str(
                server,
                proxy,
                [
                    "btrfs",
                    "property",
                    "set",
                    f"{snaps_dir}/\\$snap",
                    "ro",
                    "false",
                ],
            )


def _btrfs_del_cmd(
    dst_vol: LocalVolume | RemoteVolume,
    config: Config,
    snaps_dir: str,
) -> str:
    """Shell command to delete $snap."""
    match dst_vol:
        case LocalVolume():
            return f"btrfs subvolume delete" f' {_qp(snaps_dir)}/"$snap"'
        case RemoteVolume():
            server = config.rsync_servers[dst_vol.rsync_server]
            proxy = config.resolve_proxy(server)
            return _format_remote_command_str(
                server,
                proxy,
                [
                    "btrfs",
                    "subvolume",
                    "delete",
                    f"{snaps_dir}/\\$snap",
                ],
            )


# ── Block builders (textwrap.dedent) ─────────────────────────


def _build_check_line(
    vol: LocalVolume | RemoteVolume,
    config: Config,
    test_args: list[str],
    error_msg: str,
) -> str:
    cmd = _test_cmd(vol, config, test_args)
    return f"{cmd}" f' || {{ nbkp_log "ERROR: {error_msg}"; return 1; }}'


def _build_which_line(
    vol: LocalVolume | RemoteVolume,
    config: Config,
    command: str,
    error_msg: str,
) -> str:
    check = _which_cmd(vol, config, command)
    return f"{check}" f' || {{ nbkp_log "ERROR: {error_msg}"; return 1; }}'


def _build_preflight_block(
    sync: SyncConfig,
    config: Config,
    vol_paths: dict[str, str],
) -> str:
    """Build preflight check lines at indent 0."""
    src_vol = config.volumes[sync.source.volume]
    dst_vol = config.volumes[sync.destination.volume]
    src_path = _vol_path(vol_paths, sync.source.volume, sync.source.subdir)
    dst_path = _vol_path(
        vol_paths,
        sync.destination.volume,
        sync.destination.subdir,
    )

    lines: list[str] = []

    # Source endpoint marker
    src_marker = f"{src_path}/.nbkp-src"
    lines.append(
        _build_check_line(
            src_vol,
            config,
            ["-f", src_marker],
            f"source marker {src_marker} not found",
        )
    )

    # Destination endpoint marker
    dst_marker = f"{dst_path}/.nbkp-dst"
    lines.append(
        _build_check_line(
            dst_vol,
            config,
            ["-f", dst_marker],
            f"destination marker {dst_marker} not found",
        )
    )

    # rsync on source
    lines.append(
        _build_which_line(
            src_vol, config, "rsync", "rsync not found on source"
        )
    )

    # rsync on destination
    lines.append(
        _build_which_line(
            dst_vol,
            config,
            "rsync",
            "rsync not found on destination",
        )
    )

    # Btrfs checks
    if sync.destination.btrfs_snapshots.enabled:
        lines.append(
            _build_which_line(
                dst_vol,
                config,
                "btrfs",
                "btrfs not found on destination",
            )
        )
        latest_dir = f"{dst_path}/latest"
        lines.append(
            _build_check_line(
                dst_vol,
                config,
                ["-d", latest_dir],
                "destination latest/ directory not found" f" ({latest_dir})",
            )
        )
        snaps_dir = f"{dst_path}/snapshots"
        lines.append(
            _build_check_line(
                dst_vol,
                config,
                ["-d", snaps_dir],
                "destination snapshots/ directory not found" f" ({snaps_dir})",
            )
        )

    return "\n".join(lines)


def _build_link_dest_block(
    sync: SyncConfig,
    config: Config,
    vol_paths: dict[str, str],
) -> str:
    """Build link-dest resolution block at indent 0."""
    dst_vol = config.volumes[sync.destination.volume]
    dest_path = _vol_path(
        vol_paths,
        sync.destination.volume,
        sync.destination.subdir,
    )
    snaps_dir = f"{dest_path}/snapshots"
    ls_cmd = _ls_snapshots_cmd(dst_vol, config, snaps_dir)

    return dedent(f"""\
        NBKP_LATEST_SNAP=$({ls_cmd} 2>/dev/null | sort | tail -1)
        NBKP_LINK_DEST=""
        if [ -n "$NBKP_LATEST_SNAP" ]; then
            NBKP_LINK_DEST="--link-dest=../../snapshots/$NBKP_LATEST_SNAP"
        fi""")


def _build_rsync_block(
    sync: SyncConfig,
    config: Config,
    vol_paths: dict[str, str],
) -> str:
    """Build rsync command block at indent 0."""
    i2 = "    "  # continuation indent within this block
    cmd = build_rsync_command(
        sync, config, dry_run=False, link_dest=None, verbose=0
    )

    # Substitute local volume paths
    src_vol = config.volumes[sync.source.volume]
    dst_vol = config.volumes[sync.destination.volume]
    match (src_vol, dst_vol):
        case (RemoteVolume(), RemoteVolume()):
            pass
        case _:
            cmd[-2] = _substitute_vol_path(
                cmd[-2],
                src_vol,
                vol_paths,
                sync.source.volume,
            )
            cmd[-1] = _substitute_vol_path(
                cmd[-1],
                dst_vol,
                vol_paths,
                sync.destination.volume,
            )

    has_btrfs = sync.destination.btrfs_snapshots.enabled
    formatted = _format_shell_command(cmd, cont_indent=i2)

    runtime_vars = [
        '${NBKP_DRY_RUN_FLAG:+"$NBKP_DRY_RUN_FLAG"}',
        '${NBKP_VERBOSE_FLAG:+"$NBKP_VERBOSE_FLAG"}',
    ]
    if has_btrfs:
        runtime_vars.insert(0, '${NBKP_LINK_DEST:+"$NBKP_LINK_DEST"}')
    runtime_suffix = f" \\\n{i2}".join(runtime_vars)
    return f"{formatted} \\\n{i2}{runtime_suffix}"


def _build_snapshot_block(
    sync: SyncConfig,
    config: Config,
    vol_paths: dict[str, str],
) -> str:
    """Build btrfs snapshot block at indent 0."""
    dst_vol = config.volumes[sync.destination.volume]
    dest_path = _vol_path(
        vol_paths,
        sync.destination.volume,
        sync.destination.subdir,
    )
    latest = f"{dest_path}/latest"
    snaps_dir = f"{dest_path}/snapshots"
    snap = _snapshot_cmd(dst_vol, config, latest, snaps_dir)

    return dedent(f"""\
        if [ "$NBKP_DRY_RUN" = false ]; then
            NBKP_TS=$(date -u +%Y-%m-%dT%H:%M:%S.000Z)
            {snap}
        fi""")


def _build_prune_block(
    sync: SyncConfig,
    config: Config,
    max_snapshots: int,
    vol_paths: dict[str, str],
) -> str:
    """Build btrfs prune block at indent 0."""
    dst_vol = config.volumes[sync.destination.volume]
    dest_path = _vol_path(
        vol_paths,
        sync.destination.volume,
        sync.destination.subdir,
    )
    snaps_dir = f"{dest_path}/snapshots"
    ls_cmd = _ls_snapshots_cmd(dst_vol, config, snaps_dir)
    prop_cmd = _btrfs_prop_cmd(dst_vol, config, snaps_dir)
    del_cmd = _btrfs_del_cmd(dst_vol, config, snaps_dir)

    # fmt: off
    pipe_while = (
        'echo "$NBKP_SNAPS"'
        ' | head -n "$NBKP_EXCESS"'
        " | while IFS= read -r snap; do"
    )
    # fmt: on
    return dedent(f"""\
        if [ "$NBKP_DRY_RUN" = false ]; then
            NBKP_SNAPS=$({ls_cmd} | sort)
            NBKP_COUNT=$(echo "$NBKP_SNAPS" | wc -l | tr -d ' ')
            NBKP_EXCESS=$((NBKP_COUNT - {max_snapshots}))
            if [ "$NBKP_EXCESS" -gt 0 ]; then
                {pipe_while}
                    nbkp_log "Pruning snapshot: $snap"
                    {prop_cmd}
                    {del_cmd}
                done
            fi
        fi""")


# ── Volume check builder ────────────────────────────────────


def _build_volume_check(
    slug: str,
    vol: LocalVolume | RemoteVolume,
    config: Config,
    vol_paths: dict[str, str],
) -> str:
    vpath = vol_paths[slug]
    marker = f"{vpath}/.nbkp-vol"
    match vol:
        case LocalVolume():
            test_cmd = f"test -f {_qp(marker)}"
        case RemoteVolume():
            server = config.rsync_servers[vol.rsync_server]
            proxy = config.resolve_proxy(server)
            test_cmd = _format_remote_test(server, proxy, ["-f", marker])
    return (
        f"{test_cmd}"
        f" || {{ nbkp_log"
        f' "WARN: volume {slug}:'
        f' marker {marker} not found";'
        f" }}"
    )


# ── Disabled sync body ───────────────────────────────────────


def _build_disabled_body(
    slug: str,
    sync: SyncConfig,
    config: Config,
    vol_paths: dict[str, str],
) -> str:
    """Build the commented-out function body for a disabled sync."""
    enabled_sync = SyncConfig(
        slug=sync.slug,
        source=sync.source,
        destination=sync.destination,
        enabled=True,
        rsync_options=sync.rsync_options,
        extra_rsync_options=sync.extra_rsync_options,
        filters=sync.filters,
        filter_file=sync.filter_file,
    )
    ctx = _build_sync_context(slug, enabled_sync, config, vol_paths)

    # Render the function body the same way the template would
    lines = _render_enabled_function(ctx)
    return "\n".join(
        f"# {line}" if line.strip() else "#" for line in lines.split("\n")
    )


def _render_enabled_function(ctx: _SyncContext) -> str:
    """Render a sync function body (for disabled commenting)."""
    parts: list[str] = []
    parts.append("")
    parts.append(f"{ctx.fn_name}() {{")
    parts.append(f'    nbkp_log "Starting sync: {ctx.slug}"')
    parts.append("")
    parts.append("    # Pre-flight checks")
    for line in ctx.preflight.split("\n"):
        parts.append(f"    {line}" if line else "")
    parts.append("")
    parts.append("    # Build runtime flags")
    parts.append('    NBKP_DRY_RUN_FLAG=""')
    parts.append(
        '    if [ "$NBKP_DRY_RUN" = true ]; then'
        ' NBKP_DRY_RUN_FLAG="--dry-run"; fi'
    )
    parts.append('    NBKP_VERBOSE_FLAG=""')
    parts.append(
        '    if [ "$NBKP_VERBOSE" -ge 3 ]; then' ' NBKP_VERBOSE_FLAG="-vvv"'
    )
    parts.append(
        '    elif [ "$NBKP_VERBOSE" -ge 2 ]; then' ' NBKP_VERBOSE_FLAG="-vv"'
    )
    parts.append(
        '    elif [ "$NBKP_VERBOSE" -ge 1 ]; then' ' NBKP_VERBOSE_FLAG="-v"'
    )
    parts.append("    fi")
    if ctx.has_btrfs:
        parts.append("")
        parts.append(
            "    # Link-dest resolution"
            " (latest snapshot for incremental backup)"
        )
        for line in ctx.link_dest.split("\n"):
            parts.append(f"    {line}" if line else "")
    parts.append("")
    parts.append("    # Rsync")
    for line in ctx.rsync.split("\n"):
        parts.append(f"    {line}" if line else "")
    if ctx.has_btrfs:
        parts.append("")
        parts.append("    # Btrfs snapshot (skip if dry-run)")
        for line in ctx.snapshot.split("\n"):
            parts.append(f"    {line}" if line else "")
        if ctx.has_prune:
            parts.append("")
            parts.append(
                f"    # Prune old snapshots" f" (max: {ctx.max_snapshots})"
            )
            for line in ctx.prune.split("\n"):
                parts.append(f"    {line}" if line else "")
    parts.append("")
    parts.append(f'    nbkp_log "Completed sync: {ctx.slug}"')
    parts.append("}")
    return "\n".join(parts)


# ── Context builders ─────────────────────────────────────────


def _build_sync_context(
    slug: str,
    sync: SyncConfig,
    config: Config,
    vol_paths: dict[str, str],
) -> _SyncContext:
    """Build a _SyncContext with all pre-computed blocks."""
    has_btrfs = sync.destination.btrfs_snapshots.enabled
    btrfs_cfg = sync.destination.btrfs_snapshots
    has_prune = has_btrfs and btrfs_cfg.max_snapshots is not None

    preflight = _build_preflight_block(sync, config, vol_paths)
    link_dest = (
        _build_link_dest_block(sync, config, vol_paths) if has_btrfs else ""
    )
    rsync = _build_rsync_block(sync, config, vol_paths)
    snapshot = (
        _build_snapshot_block(sync, config, vol_paths) if has_btrfs else ""
    )
    max_snaps = btrfs_cfg.max_snapshots
    prune = (
        _build_prune_block(sync, config, max_snaps, vol_paths)
        if has_prune and max_snaps is not None
        else ""
    )

    return _SyncContext(
        slug=slug,
        fn_name=_slug_to_fn(slug),
        enabled=sync.enabled,
        has_btrfs=has_btrfs,
        has_prune=has_prune,
        max_snapshots=btrfs_cfg.max_snapshots,
        preflight=preflight,
        link_dest=link_dest,
        rsync=rsync,
        snapshot=snapshot,
        prune=prune,
    )


def _build_script_context(
    config: Config,
    options: ScriptOptions,
    vol_paths: dict[str, str],
    now: datetime,
) -> dict[str, object]:
    """Build the full template context dict."""
    timestamp = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    config_line = (
        f"# Config: {options.config_path}"
        if options.config_path
        else "# Config: <stdin>"
    )
    has_script_dir = any("$" in p for p in vol_paths.values())

    volume_checks = [
        _build_volume_check(slug, vol, config, vol_paths)
        for slug, vol in config.volumes.items()
    ]

    syncs: list[_SyncContext] = []
    for slug, sync in config.syncs.items():
        ctx = _build_sync_context(slug, sync, config, vol_paths)
        if sync.enabled:
            syncs.append(ctx)
        else:
            disabled_body = _build_disabled_body(slug, sync, config, vol_paths)
            syncs.append(
                _SyncContext(
                    slug=ctx.slug,
                    fn_name=ctx.fn_name,
                    enabled=False,
                    disabled_body=disabled_body,
                )
            )

    return {
        "timestamp": timestamp,
        "config_line": config_line,
        "has_script_dir": has_script_dir,
        "volume_checks": volume_checks,
        "syncs": syncs,
    }
