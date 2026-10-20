"""
The Coho delivery client, and the runtime generated content libraries call.

Most projects don't import this directly. They install their own content library,
generated from their content types by `coho-codegen`, which depends on this package and
gives every content type its own typed reads.
"""

from importlib.metadata import PackageNotFoundError, version

from .assets import (
    IMAGE_WIDTHS,
    RASTER_IMAGE_TYPES,
    Asset,
    AssetFile,
    FocalPoint,
    ImageAsset,
    ImageFile,
    ImageFit,
    ImageFormat,
)
from .client import (
    AsyncDeliveryClient,
    DeliveryClient,
    DeliveryConfig,
    MountedConfig,
    PreviewConfig,
    ReleasedConfig,
)
from .content import (
    AsyncContentClient,
    AsyncTypeReader,
    ContentClient,
    ContentConfig,
    Page,
    TypeReader,
)
from .env import config_from_env
from .errors import CohoDeliveryError
from .hydrate import Issue, IssueKind, Link, OnIssue, Shape, TypeShape, hydrate
from .models import (
    CohoModel,
    EntryBase,
    HydratedEntry,
    ItemBase,
    Linked,
    RepeaterItem,
    Source,
    Unresolved,
    is_resolved,
    resolved,
)
from .types import DeliveryWarning, Entry, EntryGraph, EntryList, Problem

try:
    __version__ = version("coho-delivery-sdk")
except PackageNotFoundError:  # pragma: no cover  a checkout that was never installed
    __version__ = "0+unknown"

__all__ = [
    "IMAGE_WIDTHS",
    "RASTER_IMAGE_TYPES",
    "Asset",
    "AssetFile",
    "AsyncContentClient",
    "AsyncDeliveryClient",
    "AsyncTypeReader",
    "CohoDeliveryError",
    "CohoModel",
    "ContentClient",
    "ContentConfig",
    "DeliveryClient",
    "DeliveryConfig",
    "DeliveryWarning",
    "Entry",
    "EntryBase",
    "EntryGraph",
    "EntryList",
    "FocalPoint",
    "HydratedEntry",
    "ImageAsset",
    "ImageFile",
    "ImageFit",
    "ImageFormat",
    "Issue",
    "IssueKind",
    "ItemBase",
    "Link",
    "Linked",
    "MountedConfig",
    "OnIssue",
    "Page",
    "PreviewConfig",
    "Problem",
    "ReleasedConfig",
    "RepeaterItem",
    "Shape",
    "Source",
    "TypeReader",
    "TypeShape",
    "Unresolved",
    "__version__",
    "config_from_env",
    "hydrate",
    "is_resolved",
    "resolved",
]
