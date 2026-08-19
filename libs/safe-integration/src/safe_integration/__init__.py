"""safe_integration — Protocol interfaces for SAFE app integration.

Each Protocol is opt-in. An app imports only the contracts it uses:

  from safe_integration import IntakeClient, set_intake_client
  from safe_integration import SAFESession
  from safe_integration import IdentityClient, set_identity_client

Every contract follows the willow-read pattern: Protocol + set_client()
injection + silent no-op when no client is injected.
"""
from safe_integration.intake import (
    IntakeClient, set_intake_client, get_intake_client, contribute,
)
from safe_integration.session import SAFESession
from safe_integration.identity import (
    IdentityClient, set_identity_client, get_identity_client,
    get_user_uuid, write_session_composite,
)

__all__ = [
    "IntakeClient", "set_intake_client", "get_intake_client", "contribute",
    "SAFESession",
    "IdentityClient", "set_identity_client", "get_identity_client",
    "get_user_uuid", "write_session_composite",
]
