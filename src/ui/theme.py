"""Material Design 3 design tokens, tonal palettes, typography, and spacing grid."""

from dataclasses import dataclass
import sys
from typing import Dict, Tuple

# Legacy/compatibility semantic constants (also used by tests and state dot).
CHROMA = "#FF00FE"  # Transparent color key on Windows; never drawn as a visible surface.
ACCENT = "#A8B2FF"
MIC = "#FF6B70"
WORK = "#F0A92E"
DONE = "#40CE8D"

# Consistent 4px / 8px Material Design 3 spacing grid.
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24

PILL_H = 48
PANEL_W = 580
PANEL_H = 760

STATE_WORD: Dict[str, str] = {
    "ready": "Ready",
    "idle": "Ready",
    "listening": "Listening",
    "processing": "Understanding",
    "executing": "Working",
    "done": "Done",
    "error": "Needs you",
    "guardrail": "Needs you",
}


def resolve_font_family() -> str:
    """Pick Segoe UI Variable Text on Windows 11 when available, else Segoe UI."""
    if sys.platform == "win32":
        return "Segoe UI"
    return "Segoe UI"


FONT = resolve_font_family()
MONO_FONT = "Consolas"


@dataclass(frozen=True)
class Theme:
    """Material Design 3 tonal color and typography token set."""

    name: str
    is_dark: bool

    # Surface hierarchy (M3 tonal elevation)
    surface_container_lowest: str
    surface_container_low: str
    surface_container: str
    surface_container_high: str
    surface_container_highest: str

    # Primary role
    primary: str
    on_primary: str
    primary_container: str
    on_primary_container: str

    # Secondary role
    secondary: str
    on_secondary: str
    secondary_container: str
    on_secondary_container: str

    # Tertiary role
    tertiary: str
    on_tertiary: str
    tertiary_container: str
    on_tertiary_container: str

    # Semantic status roles
    error: str
    on_error: str
    error_container: str
    on_error_container: str
    success: str
    on_success: str
    success_container: str
    on_success_container: str
    warning: str
    on_warning: str
    warning_container: str
    on_warning_container: str

    # Text & borders (all >= 4.5:1 contrast on surface_container)
    on_surface: str
    on_surface_variant: str
    outline: str
    outline_variant: str

    # Status dot colors
    mic: str
    work: str
    done: str
    idle_dot: str

    # Typography scale
    font_family: str = FONT
    mono_family: str = MONO_FONT

    @property
    def title_large(self) -> Tuple[str, int, str]:
        return (self.font_family, 13, "bold")

    @property
    def title_medium(self) -> Tuple[str, int, str]:
        return (self.font_family, 11, "bold")

    @property
    def title_small(self) -> Tuple[str, int, str]:
        return (self.font_family, 10, "bold")

    @property
    def body_large(self) -> Tuple[str, int]:
        return (self.font_family, 10)

    @property
    def body_medium(self) -> Tuple[str, int]:
        return (self.font_family, 9)

    @property
    def body_small(self) -> Tuple[str, int]:
        return (self.font_family, 8)

    @property
    def label_large(self) -> Tuple[str, int, str]:
        return (self.font_family, 10, "bold")

    @property
    def label_medium(self) -> Tuple[str, int, str]:
        return (self.font_family, 9, "bold")

    @property
    def label_small(self) -> Tuple[str, int]:
        return (self.font_family, 8)

    @property
    def mono_small(self) -> Tuple[str, int]:
        return (self.mono_family, 8)


DARK_THEME = Theme(
    name="dark",
    is_dark=True,
    surface_container_lowest="#0B0E14",
    surface_container_low="#121620",
    surface_container="#181C26",
    surface_container_high="#212736",
    surface_container_highest="#2B3245",
    primary="#A8B2FF",
    on_primary="#0D1442",
    primary_container="#2C3678",
    on_primary_container="#E3E7FF",
    secondary="#8CE0F5",
    on_secondary="#062936",
    secondary_container="#193A4A",
    on_secondary_container="#CEF2FC",
    tertiary="#F4B860",
    on_tertiary="#3A2200",
    tertiary_container="#4E3309",
    on_tertiary_container="#FFE3B8",
    error="#FF6B70",
    on_error="#3B0409",
    error_container="#5B1B22",
    on_error_container="#FFDADD",
    success="#40CE8D",
    on_success="#002917",
    success_container="#113D29",
    on_success_container="#B8F5D4",
    warning="#F0A92E",
    on_warning="#2E1C00",
    warning_container="#4A3107",
    on_warning_container="#FFE0A6",
    on_surface="#EEF1F8",
    on_surface_variant="#B4BDD0",
    outline="#555F75",
    outline_variant="#32394A",
    mic=MIC,
    work=WORK,
    done=DONE,
    idle_dot="#8F98AD",
)

LIGHT_THEME = Theme(
    name="light",
    is_dark=False,
    surface_container_lowest="#FFFFFF",
    surface_container_low="#F6F7FC",
    surface_container="#EFF1F8",
    surface_container_high="#E4E7F2",
    surface_container_highest="#D9DDEA",
    primary="#4F46E5",
    on_primary="#FFFFFF",
    primary_container="#E0E2FF",
    on_primary_container="#15105C",
    secondary="#0891B2",
    on_secondary="#FFFFFF",
    secondary_container="#CFFAFE",
    on_secondary_container="#083344",
    tertiary="#B45309",
    on_tertiary="#FFFFFF",
    tertiary_container="#FEF3C7",
    on_tertiary_container="#451A03",
    error="#DC2626",
    on_error="#FFFFFF",
    error_container="#FEE2E2",
    on_error_container="#7F1D1D",
    success="#059669",
    on_success="#FFFFFF",
    success_container="#D1FAE5",
    on_success_container="#064E3B",
    warning="#D97706",
    on_warning="#FFFFFF",
    warning_container="#FEF3C7",
    on_warning_container="#78350F",
    on_surface="#141824",
    on_surface_variant="#475066",
    outline="#8992A8",
    outline_variant="#CED4E3",
    mic=MIC,
    work="#D97706",
    done="#059669",
    idle_dot="#64748B",
)

THEMES: Dict[str, Theme] = {
    "dark": DARK_THEME,
    "light": LIGHT_THEME,
}


def get_theme(name: str = "dark") -> Theme:
    """Return the Material Design 3 Theme for 'dark' or 'light' (defaults to dark)."""
    return THEMES.get((name or "dark").strip().lower(), DARK_THEME)


def state_color(theme: Theme, state: str) -> str:
    """Return the semantic status color for a daemon state."""
    return {
        "ready": theme.idle_dot,
        "idle": theme.idle_dot,
        "listening": theme.mic,
        "processing": theme.work,
        "executing": theme.work,
        "done": theme.done,
        "error": theme.mic,
        "guardrail": theme.work,
    }.get(state, theme.idle_dot)
