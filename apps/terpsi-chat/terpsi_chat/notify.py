"""Outbound notification to a guardian's phone — pointer only, never payload.

The architecture is LAN-served with a single outbound to home base. That
outbound triggers an SMS whose entire job is to say something exists. Content
stays on the LAN.

Why this is a module with a mechanism in it rather than a convention:

SMS is unencrypted, visible to the carrier, visible on a lock screen, and
visible to anyone holding the phone — including in the household the design
cannot see into. So the SMS body must never carry message content, sender
identity, or a subject line.

The pressure to enrich it will be constant and will always sound reasonable.
"Just say who it's from." "Just flag the urgent ones." Each increment moves
content onto that channel. The mechanism that resists it is here:
`render_notice` takes a template key and nothing else. There is no parameter
into which content could be interpolated, so adding a preview requires changing
this function's signature, which is a visible act rather than a passing edit.

Templates are asserted content-free by test_gates.py — no format placeholders,
no names, no interpolation syntax of any kind.
"""

# The complete set of things an outbound SMS may say. Adding an entry is fine.
# Adding a placeholder to one is a gate failure.
NOTICE_TEMPLATES = {
    "waiting": "You have something waiting in the Terpsi portal.",
    "action_needed": "Something in the Terpsi portal needs your attention.",
    "contact_request": "There is a request waiting for you in the Terpsi portal.",
    "access_notice": "There is a notice waiting for you in the Terpsi portal.",
}

# Interpolation syntax in any form. If a template contains one of these, some
# caller somewhere intends to fill it, and the fill will be content.
_PLACEHOLDER_MARKERS = ("{", "}", "%s", "%d", "%(", "$", "<", "format(")


class NoticeTemplateError(ValueError):
    """Raised when a caller asks for a notice that is not in the fixed set."""


def render_notice(template_key: str) -> str:
    """Return the SMS body for `template_key`.

    Deliberately takes no other argument. A caller that wants to include a
    name, a preview, or a subject has nowhere to put it — which is the point.
    """
    try:
        return NOTICE_TEMPLATES[template_key]
    except KeyError:
        raise NoticeTemplateError(
            f"no such notice template: {template_key!r}; "
            f"known keys are {sorted(NOTICE_TEMPLATES)}"
        ) from None
