"""Source-neutral metadata for canonical NEMO observations; no generator dependencies."""

from dataclasses import dataclass

LEGACY_CHANNELS = {"paid_search": True, "organic_search": False, "direct": False}
LEGACY_DEVICES = ("android", "ios", "desktop")


@dataclass(frozen=True)
class SourceContract:
    schema_version: str
    mode: str
    dataset_id: str
    channels: dict[str, bool]
    devices: tuple[str, ...]


def source_contract(manifest: dict) -> SourceContract:
    version = manifest.get("schema_version")
    mode = manifest.get("mode")
    if version == "1":
        if mode != "synthetic":
            raise ValueError("legacy schema 1 is the synthetic reference format")
        return SourceContract("1", mode, "legacy-synthetic", dict(LEGACY_CHANNELS), LEGACY_DEVICES)
    if version != "2" or mode not in ("synthetic", "production"):
        raise ValueError("unsupported canonical schema or source mode")
    dataset_id = manifest.get("dataset_id")
    channels = manifest.get("channels")
    devices = manifest.get("devices")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("canonical schema 2 requires a dataset_id")
    if (
        not isinstance(channels, dict)
        or not channels
        or any(
            not isinstance(k, str) or not k.strip() or type(v) is not bool
            for k, v in channels.items()
        )
    ):
        raise ValueError("channels must map canonical channel names to explicit paid-media flags")
    if (
        not isinstance(devices, list)
        or not devices
        or any(not isinstance(v, str) or not v.strip() for v in devices)
        or len(set(devices)) != len(devices)
    ):
        raise ValueError("devices must be unique canonical device names")
    return SourceContract(version, mode, dataset_id, dict(channels), tuple(devices))
