"""Tests for the credential guard — run from inside apps/nest-seed/.

Token fixtures are SYNTHETIC, assembled from parts so no real-looking secret
literal lives in source (which would trip GitHub push protection). They match
the detector's shape without being valid credentials.
"""
from nest_pipeline import secrets as s
from nest_pipeline import classify as cl

# synthetic: matches discord_token shape ([MN]{24}.{6}.{27,}) but is clearly fake
_DISCORD = ".".join(["M" + "q" * 24, "aB3dEf", "z" * 30])
# synthetic: matches jwt shape (eyJ….eyJ….…)
_JWT = ".".join(["eyJ" + "a" * 12, "eyJ" + "b" * 12, "c" * 20])


def test_find_discord_and_jwt():
    kinds = {k for k, _ in s.find_secrets(f"token is {_DISCORD} and {_JWT}")}
    assert "discord_token" in kinds and "jwt" in kinds


def test_find_assigned_credential_skips_placeholders():
    assert s.find_secrets('api_key = "REPLACE_your_key_here_xxxx"') == []
    got = s.find_secrets("password: hunter2_supersecret_value")
    assert got and got[0][0] == "credential"


def test_redact_value_is_safe():
    r = s.redact_value(_DISCORD)
    assert _DISCORD not in r and "…" in r and r.startswith("Mqqqqq")


def test_redact_text_removes_raw_secret():
    out = s.redact_text(f"here {_DISCORD} ok")
    assert _DISCORD not in out and "[REDACTED:discord_token]" in out


def test_classify_emits_secret_fragment_and_scrubs():
    frags = cl.classify(f"my bot token {_DISCORD}", filename="discord.txt")
    secret = [f for f in frags if f.fragment_type == "secret"]
    assert secret and secret[0].label == "discord_token"
    assert secret[0].confidence == "confirmed"
    assert all(_DISCORD not in f.content for f in frags)


def test_clean_text_has_no_secret_fragment():
    frags = cl.classify("just an ordinary note about the weather", filename="n.md")
    assert not any(f.fragment_type == "secret" for f in frags)
