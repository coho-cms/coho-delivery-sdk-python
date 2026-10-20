"""
Assets, and their URLs: an image resized on request, a set of widths for `srcset`, and a
file to download. Built from what the asset carries, with no request and no secret.

The edge serves an asset two ways: `url`, the original bytes of any file, and for raster
images only `image_url`, which resizes on request from query parameters. The edge normalizes
what it is sent, snapping widths up to `IMAGE_WIDTHS`, so these only spell the request; they
never resize.

An asset is as public as its URL, drafts included, and deleting it does not stop its URL
working.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal
from urllib.parse import quote

from pydantic import Field

from .models import CohoModel

ImageFit = Literal["scale", "pad", "fill", "crop", "thumb"]
"""
How to resize an image. `scale`, the default, keeps the aspect ratio; `fill` crops to exactly
the width and height around the focal point, as `crop` and `thumb` do; `pad` fits the image
inside them, on `background`.
"""

ImageFormat = Literal["auto", "avif", "webp", "jpg", "png"]
"""`auto` lets the edge pick AVIF, WebP or JPEG from what the browser accepts."""

IMAGE_WIDTHS: tuple[int, ...] = (
    16, 32, 48, 64, 96, 128, 192, 256, 320, 384, 480, 640, 750, 828, 960, 1080, 1200, 1440,
    1600, 1920, 2048, 2560, 3840,
)  # fmt: skip
"""The widths the edge serves. A requested width snaps up to the next one."""

RESPONSIVE_WIDTHS: tuple[int, ...] = tuple(width for width in IMAGE_WIDTHS if width >= 640)
"""The widths a responsive `srcset` offers by default: phones up to large screens."""

RASTER_IMAGE_TYPES: tuple[str, ...] = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/avif",
    "image/heic",
)
"""The media types an `ImageAsset` can be: the raster images the edge resizes."""


class FocalPoint(CohoModel):
    """Where a crop centres, as fractions of the width and height."""

    x: float
    y: float


class AssetFile(CohoModel):
    """The bytes behind an asset, as the server sniffed them."""

    filename: str | None = None
    media_type: str | None = Field(default=None, alias="mediaType")
    byte_size: int | None = Field(default=None, alias="byteSize")

    width: int | None = None
    """Raster images only, as is `height`."""

    height: int | None = None


class ImageFile(AssetFile):
    """The bytes behind a raster image, which always has dimensions."""

    width: int
    height: int


class Asset(CohoModel):
    """
    An asset, as delivery embeds it in the entry that links it. Only what URLs are built from
    is needed; the rest is there for the page, such as `alt` for an image.
    """

    id: str | None = None
    """The asset's id: what the entry's field links."""

    url: str | None = None
    """The original bytes, from the asset CDN."""

    image_url: str | None = Field(default=None, alias="imageUrl")
    """Raster images only: the base that resizes on request. Use `image()` to build a URL."""

    file: AssetFile | None = None

    focal_point: FocalPoint | None = Field(default=None, alias="focalPoint")

    title: str | None = None
    alt: str | None = None

    @property
    def is_image(self) -> bool:
        """Whether the edge resizes it: a raster image."""
        return self.image_url is not None

    def image(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
        fit: ImageFit | None = None,
        format: ImageFormat | None = None,
        quality: int | None = None,
        background: str | None = None,
    ) -> str:
        """
        The asset's URL, resized when asked. A file that is not a raster image, such as an SVG
        or a PDF, has no resizing, so its original is returned whatever the options.

        `quality` is 1 to 100, which the edge rounds to a multiple of 5; its default is 75.
        `background` is the colour around a `pad`, as `rrggbb`.
        """
        query = self._image_query(width, height, fit, format, quality, background)
        if query == "" or self.image_url is None:
            return self._original()
        return f"{self.image_url}?{query}"

    def srcset(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
        fit: ImageFit | None = None,
        format: ImageFormat | None = None,
        quality: int | None = None,
        background: str | None = None,
        widths: Sequence[int] | None = None,
        densities: Sequence[float] | None = None,
    ) -> str:
        """
        A `srcset` for the asset: `url 640w, url 750w, …` for a responsive image, or
        `url 1x, url 2x` with `densities` for one shown at a fixed `width`. Widths beyond the
        original are left out, since the edge never enlarges. A file that is not a raster
        image has one candidate, its original.
        """
        if self.image_url is None:
            return self._original()

        ratio = height / width if width is not None and height is not None else None

        def at(each: int) -> str:
            tall = round(each * ratio) if ratio is not None else None
            return self.image(
                width=each,
                height=tall,
                fit=fit,
                format=format,
                quality=quality,
                background=background,
            )

        if densities is not None:
            if width is None:
                raise ValueError("srcset with densities needs a width")
            return ", ".join(f"{at(round(width * d))} {_density(d)}x" for d in densities)

        largest = self.file.width if self.file is not None else None
        offered = sorted(
            {each for each in (widths or RESPONSIVE_WIDTHS) if largest is None or each <= largest}
        )
        # An image smaller than every width offered is still offered, at its own size.
        if not offered and largest is not None:
            offered = [largest]
        return ", ".join(f"{at(each)} {each}w" for each in offered)

    def download(self) -> str:
        """
        A URL that downloads the asset rather than opening it: the original, with `dl=1`
        asking the edge to send it as an attachment under its filename. A browser ignores the
        `download` attribute on a link to another origin, which the asset CDN is.

        The edge does not honour `dl` yet. Until it does, the file opens in the browser as
        `url` does; the link needs no change when it starts to.
        """
        url = self._original()
        return f"{url}{'&' if '?' in url else '?'}dl=1"

    def _image_query(
        self,
        width: int | None,
        height: int | None,
        fit: ImageFit | None,
        format: ImageFormat | None,
        quality: int | None,
        background: str | None,
    ) -> str:
        """The query the edge resizes from, in a fixed order, so equal options make equal URLs."""
        params: list[tuple[str, str | int | float | None]] = [
            ("w", width),
            ("h", height),
            ("fit", fit),
            ("fm", format),
            ("q", quality),
            ("bg", background),
        ]
        # The edge cannot look the focal point up, so a crop is told where to centre.
        focal = self.focal_point
        if focal is not None and fit in ("fill", "crop", "thumb"):
            params += [("fx", _round2(focal.x)), ("fy", _round2(focal.y))]
        return "&".join(
            f"{name}={quote(str(value), safe='')}" for name, value in params if value is not None
        )

    def _original(self) -> str:
        if self.url is None:
            raise ValueError("This asset has no URL: the deployment serving it has no asset CDN")
        return self.url


class ImageAsset(Asset):
    """
    An asset whose field accepts only raster images, so it always has dimensions and resizes
    at the edge. A field that also accepts SVG, or any image, is an `Asset`.
    """

    image_url: str = Field(alias="imageUrl")
    file: ImageFile


def _round2(value: float) -> float | int:
    rounded = round(value * 100) / 100
    return int(rounded) if rounded == int(rounded) else rounded


def _density(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)
