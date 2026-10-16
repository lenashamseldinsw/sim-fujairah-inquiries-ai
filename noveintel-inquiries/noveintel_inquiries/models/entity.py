"""
The tenant identity pack — what Module 03 (Self-Service Branding) will eventually own.

Section 5 of the prerequisites brief assigns organisation name, logo, brand colours
and the closing statement to the client profile. Until that module exists there is no
store to read them from, so they travel on the request and this model is their
contract.

**No tenant-specific defaults.** A caller supplies its own identity or the request is
rejected: names are required, everything else is optional and simply absent when not
given. Defaulting any field to a particular organisation's value would mean a tenant
that supplies a name but no logo silently prints someone else's logo — the sort of
mistake nobody catches until it is printed. The only defaults here are platform-level:
the NoveAI brand palette, which belongs to no tenant.

**Colours default to the documented palette.** Prerequisites §5: the report adopts
the tenant's brand; NoveAI Navy (#201853) and Magenta (#7E2362) are the default. A
request that sends no ``brand`` is drawn in that default; one that sends ``brand`` is
drawn in the tenant's colours. Two things are deliberately *not* tenant-configurable:

  * the status palette — within / near / over deadline, the same triple as Domain
    01's compliant / watch / breach — platform-locked and defined here as
    ``STATUS_COLORS``. A red that means "over deadline" must read the same for every
    tenant;
  * anything the analysis computes — branding never reaches a model call.
"""
from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "BrandColors",
    "EntityInfo",
    "STATUS_COLORS",
    "TIMELINESS_COLORS",
    "NOVEAI_NAVY",
    "NOVEAI_MAGENTA",
]

# ── Platform defaults ─────────────────────────────────────────────────────────
NOVEAI_NAVY = "#201853"
NOVEAI_MAGENTA = "#7E2362"

# Platform-locked status colours (Section 5, BO decision 2026-07-07). These are NOT
# tenant-configurable: a compliant cell must read the same across every tenant.
STATUS_COLORS: dict[str, str] = {
    "compliant": "#2E8B6B",
    "watch": "#C68A2E",
    "breach": "#B5393F",
}

# The same triple under the timeliness names the report prints (Prerequisites §5).
TIMELINESS_COLORS: dict[str, str] = {
    "within": STATUS_COLORS["compliant"],
    "near": STATUS_COLORS["watch"],
    "over": STATUS_COLORS["breach"],
    "unspecified": "#9AA0A6",
}

HexColor = Annotated[str, Field(pattern=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")]

_DATA_URI_RE = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,")


class BrandColors(BaseModel):
    """The tenant's two-colour brand palette, used for headings, banners and charts."""

    primary: HexColor = Field(
        default=NOVEAI_NAVY,
        description=(
            "Primary brand colour: headings, banners, table headers, the cover and "
            "each chart's accent series. Defaults to NoveAI Navy (Prerequisites §5)."
        ),
    )
    secondary: HexColor = Field(
        default=NOVEAI_MAGENTA,
        description=(
            "Secondary brand colour: accents and the second chart series. Defaults "
            "to NoveAI Magenta (Prerequisites §5)."
        ),
    )


class EntityInfo(BaseModel):
    """Identity and branding of the organisation the report is produced for."""

    name_ar: str = Field(
        description="Organisation name in Arabic. Used when the report language is 'ar'."
    )
    name_en: str = Field(
        description="Organisation name in English. Used when the report language is 'en'."
    )
    name_short: str | None = Field(
        default=None,
        description=(
            "Short-form identity line printed under the organisation name on the "
            "cover, the same in both languages — typically the English short name or "
            "initialism. Omit to print the name alone."
        ),
    )
    logo_path: str | None = Field(
        default=None,
        description=(
            "Filesystem path to the organisation logo. Convenient for local and "
            "embedded use, and read from the *server's* disk — almost never what a "
            "caller means over HTTP. Mutually exclusive with logo_base64."
        ),
    )
    logo_base64: str | None = Field(
        default=None,
        description=(
            "Organisation logo as base64, with or without a data: URI prefix. The "
            "form that survives an HTTP boundary. Mutually exclusive with logo_path."
        ),
    )
    brand: BrandColors = Field(
        default_factory=BrandColors,
        description=(
            "Brand palette for headings, banners and chart series. Status colours are "
            "platform-locked and are not part of this."
        ),
    )
    closing_statement: str | None = Field(
        default=None,
        description=(
            "The entity's vision statement (Module 03). The report's closing "
            "statement is written to tie back to it, and it is printed beneath the "
            "closing. Omit to close without one."
        ),
    )
    center_name_ar: str | None = Field(
        default=None,
        description="Service centre / sector name in Arabic, shown on the cover page.",
    )
    center_name_en: str | None = Field(
        default=None,
        description="Service centre / sector name in English, shown on the cover page.",
    )

    @model_validator(mode="after")
    def _at_most_one_logo_source(self) -> EntityInfo:
        """A logo may be given as a path or as base64 — not both, and not required.

        A tenant without a logo gets a cover without one, which is a cosmetic
        shortcoming rather than a reason to reject the run.
        """
        if self.logo_path and self.logo_base64:
            raise ValueError("Provide either logo_path or logo_base64, not both.")
        return self

    def name(self, lang: str) -> str:
        """Organisation name for the given report language."""
        return self.name_ar if lang == "ar" else self.name_en

    def center_name(self, lang: str) -> str:
        """Service centre name for the given report language, or an empty string."""
        return (self.center_name_ar if lang == "ar" else self.center_name_en) or ""

    def logo_bytes(self) -> bytes | None:
        """The logo as raw image bytes, however it was supplied. None if there is none."""
        if self.logo_path:
            return Path(self.logo_path).read_bytes()
        if not self.logo_base64:
            return None
        payload = _DATA_URI_RE.sub("", self.logo_base64)
        try:
            return base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("logo_base64 is not valid base64.") from exc
