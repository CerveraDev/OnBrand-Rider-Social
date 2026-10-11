"""Social medium runtime: static posts and carousels from approved project inputs.

Sibling of `tools.rider_campaign_runtime`. It imports nothing from the email
runtime so a broker bundle can ship without it.
"""

from .runtime import BuildResult, SocialRuntimeError, build_social, build_social_from_spec
from .schema import SocialSpecError, validate_social_spec

__all__ = [
    "BuildResult",
    "SocialRuntimeError",
    "SocialSpecError",
    "build_social",
    "build_social_from_spec",
    "validate_social_spec",
]
