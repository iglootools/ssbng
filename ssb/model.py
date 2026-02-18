"""Pydantic-based data models for SSB backup configuration and status."""

from __future__ import annotations
from typing import Optional, List, Dict, Union
from pydantic import BaseModel, Field, model_validator, field_validator
import enum

class LocalVolume(BaseModel):
	model_config = {"frozen": True}
	"""A local filesystem volume."""
	name: str = Field(..., min_length=1)
	path: str = Field(..., min_length=1)

class RemoteVolume(BaseModel):
	model_config = {"frozen": True}
	"""A remote volume accessible via SSH."""
	name: str = Field(..., min_length=1)
	host: str = Field(..., min_length=1)
	path: str = Field(..., min_length=1)
	port: int = Field(22, ge=1, le=65535)
	user: Optional[str] = None
	ssh_key: Optional[str] = None
	ssh_options: List[str] = Field(default_factory=list)

Volume = Union[LocalVolume, RemoteVolume]

class SyncEndpoint(BaseModel):
	"""A sync endpoint referencing a volume by name."""
	volume_name: str = Field(..., min_length=1)
	subdir: Optional[str] = None

class SyncConfig(BaseModel):
	"""Configuration for a single sync operation."""
	name: str = Field(..., min_length=1)
	source: SyncEndpoint
	destination: SyncEndpoint
	enabled: bool = True
	btrfs_snapshots: bool = False

class Config(BaseModel):
	"""Top-level SSB configuration."""
	volumes: Dict[str, Volume] = Field(default_factory=dict)
	syncs: Dict[str, SyncConfig] = Field(default_factory=dict)

	@field_validator('volumes', mode='before')
	@classmethod
	def parse_volumes(cls, v):
		if not isinstance(v, dict):
			raise ValueError("'volumes' must be a mapping")
		result = {}
		for name, data in v.items():
			# Allow already-instantiated model objects
			if isinstance(data, (LocalVolume, RemoteVolume)):
				result[name] = data
				continue
			if not isinstance(data, dict):
				raise ValueError(f"Volume '{name}' must be a mapping")
			vol_type = data.get("type")
			if vol_type == "local":
				path = data.get("path")
				if not path:
					raise ValueError(f"Local volume '{name}' requires 'path'")
				result[name] = LocalVolume(name=name, path=path)
			elif vol_type == "remote":
				host = data.get("host")
				path = data.get("path")
				if not host or not path:
					raise ValueError(f"Remote volume '{name}' requires 'host' and 'path'")
				result[name] = RemoteVolume(
					name=name,
					host=host,
					path=path,
					port=data.get("port", 22),
					user=data.get("user"),
					ssh_key=data.get("ssh_key"),
					ssh_options=data.get("ssh_options", []),
				)
			else:
				raise ValueError(f"Volume '{name}' has invalid type: {vol_type}")
		return result

	@field_validator('syncs', mode='before')
	@classmethod
	def parse_syncs(cls, v):
		if not isinstance(v, dict):
			raise ValueError("'syncs' must be a mapping")
		result = {}
		for name, data in v.items():
			# Allow already-instantiated model objects
			if isinstance(data, SyncConfig):
				result[name] = data
				continue
			if not isinstance(data, dict):
				raise ValueError(f"Sync '{name}' must be a mapping")
			source_data = data.get("source")
			dest_data = data.get("destination")
			if not isinstance(source_data, dict):
				raise ValueError(f"Sync '{name}' requires 'source' mapping")
			if not isinstance(dest_data, dict):
				raise ValueError(f"Sync '{name}' requires 'destination' mapping")
			source_vol = source_data.get("volume")
			if not source_vol:
				raise ValueError(f"Sync '{name}' source requires 'volume'")
			dest_vol = dest_data.get("volume")
			if not dest_vol:
				raise ValueError(f"Sync '{name}' destination requires 'volume'")
			result[name] = SyncConfig(
				name=name,
				source=SyncEndpoint(
					volume_name=source_vol,
					subdir=source_data.get("subdir"),
				),
				destination=SyncEndpoint(
					volume_name=dest_vol,
					subdir=dest_data.get("subdir"),
				),
				enabled=data.get("enabled", True),
				btrfs_snapshots=data.get("btrfs_snapshots", False),
			)
		return result

	@model_validator(mode="after")
	def validate_cross_references(self):
		for sync_name, sync in self.syncs.items():
			if sync.source.volume_name not in self.volumes:
				raise ValueError(f"Sync '{sync_name}' references unknown source volume '{sync.source.volume_name}'")
			if sync.destination.volume_name not in self.volumes:
				raise ValueError(f"Sync '{sync_name}' references unknown destination volume '{sync.destination.volume_name}'")
		return self

class VolumeStatus(BaseModel):
	"""Runtime status of a volume."""
	name: str
	config: Volume
	active: bool
	reason: str

class SyncStatus(BaseModel):
	"""Runtime status of a sync."""
	name: str
	config: SyncConfig
	source_status: VolumeStatus
	destination_status: VolumeStatus
	active: bool
	reason: str

class SyncResult(BaseModel):
	"""Result of running a sync."""
	sync_name: str
	success: bool
	dry_run: bool
	rsync_exit_code: int
	output: str
	snapshot_path: Optional[str] = None
	error: Optional[str] = None

class OutputFormat(str, enum.Enum):
	"""Output format for CLI commands."""
	HUMAN = "human"
	JSON = "json"
