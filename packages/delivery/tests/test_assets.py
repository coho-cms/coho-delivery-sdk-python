from __future__ import annotations

import pytest

from coho_delivery_sdk import IMAGE_WIDTHS, Asset, AssetFile, ImageAsset

BASE = "https://assets.test/p1"

PHOTO = Asset.model_validate(
    {
        "url": f"{BASE}/a/abc/culvert.png",
        "imageUrl": f"{BASE}/i/abc/culvert.png",
        "file": {
            "filename": "culvert.png",
            "mediaType": "image/png",
            "width": 2000,
            "height": 1000,
        },
        "focalPoint": {"x": 0.25, "y": 0.333},
        "alt": "A culvert under Elm Street",
    }
)

PDF = Asset.model_validate(
    {
        "url": f"{BASE}/a/def/roundabout-functionality.pdf",
        "file": {
            "filename": "roundabout-functionality.pdf",
            "mediaType": "application/pdf",
            "byteSize": 52000,
        },
    }
)


def test_an_image_with_no_options_is_its_original() -> None:
    assert PHOTO.image() == PHOTO.url


def test_a_resize_goes_to_the_image_base_its_parameters_in_a_fixed_order() -> None:
    assert (
        PHOTO.image(quality=80, format="auto", width=800)
        == f"{BASE}/i/abc/culvert.png?w=800&fm=auto&q=80"
    )


def test_a_crop_centres_on_the_focal_point_rounded_to_two_decimals() -> None:
    assert (
        PHOTO.image(width=400, height=400, fit="fill")
        == f"{BASE}/i/abc/culvert.png?w=400&h=400&fit=fill&fx=0.25&fy=0.33"
    )
    # A scale keeps the whole image, so it has nothing to centre.
    assert PHOTO.image(width=400, fit="scale") == f"{BASE}/i/abc/culvert.png?w=400&fit=scale"


def test_a_file_that_is_not_a_raster_image_is_its_original_whatever_the_options() -> None:
    assert PDF.image(width=400) == PDF.url
    assert PDF.srcset() == PDF.url
    assert not PDF.is_image


def test_a_responsive_srcset_offers_the_edge_widths_from_640_up_to_the_original() -> None:
    candidates = PHOTO.srcset(format="auto").split(", ")
    assert [c.split(" ")[1] for c in candidates] == [
        f"{w}w" for w in IMAGE_WIDTHS if 640 <= w <= 2000
    ]
    assert candidates[0] == f"{BASE}/i/abc/culvert.png?w=640&fm=auto 640w"


def test_given_widths_are_sorted_and_deduplicated_and_a_crop_keeps_its_shape_at_each() -> None:
    assert PHOTO.srcset(widths=[800, 400, 800], width=400, height=200, fit="fill") == ", ".join(
        [
            f"{BASE}/i/abc/culvert.png?w=400&h=200&fit=fill&fx=0.25&fy=0.33 400w",
            f"{BASE}/i/abc/culvert.png?w=800&h=400&fit=fill&fx=0.25&fy=0.33 800w",
        ]
    )


def test_an_image_smaller_than_every_width_is_offered_at_its_own_size() -> None:
    icon = PHOTO.model_copy(update={"file": AssetFile(width=120, height=120)})
    assert icon.srcset() == f"{BASE}/i/abc/culvert.png?w=120 120w"


def test_densities_give_1x_and_2x_of_a_fixed_width() -> None:
    assert (
        PHOTO.srcset(width=300, densities=[1, 2])
        == f"{BASE}/i/abc/culvert.png?w=300 1x, {BASE}/i/abc/culvert.png?w=600 2x"
    )
    with pytest.raises(ValueError, match="needs a width"):
        PHOTO.srcset(densities=[1, 2])


def test_a_download_is_the_original_asked_for_as_an_attachment() -> None:
    assert PDF.download() == f"{PDF.url}?dl=1"
    assert Asset(url="https://assets.test/a?v=1").download() == "https://assets.test/a?v=1&dl=1"


def test_an_asset_with_no_url_is_refused_not_linked_to_nothing() -> None:
    with pytest.raises(ValueError, match="no URL"):
        Asset().download()
    with pytest.raises(ValueError, match="no URL"):
        Asset().image()


def test_an_image_asset_always_has_dimensions() -> None:
    image = ImageAsset.model_validate(PHOTO.model_dump())
    assert (image.file.width, image.file.height) == (2000, 1000)
    with pytest.raises(ValueError):
        ImageAsset.model_validate(PDF.model_dump())


def test_an_asset_serializes_as_delivery_sent_it() -> None:
    dumped = PHOTO.model_dump(exclude_none=True)
    assert dumped["imageUrl"] == f"{BASE}/i/abc/culvert.png"
    assert dumped["focalPoint"] == {"x": 0.25, "y": 0.333}
    assert dumped["file"]["mediaType"] == "image/png"
