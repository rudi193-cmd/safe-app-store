"""safe_integration — story-timeline bridge to libs/safe-integration.

Configures the identity module with this app's vault path and re-exports
get_user_uuid / write_session_composite so callers keep using
`safe_integration.get_user_uuid()` unchanged.
"""
from story_paths import vault_root
from safe_integration.identity import (
    set_identity_client, get_user_uuid, write_session_composite,
)

set_identity_client(None, app_id="story-timeline",
                    identity_path=vault_root() / "user_identity.json")

__all__ = ["get_user_uuid", "write_session_composite"]
