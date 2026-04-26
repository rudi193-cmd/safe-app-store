"""
Audit Engine
=============
Routes claims to data sources, compares findings, produces verdicts.
"""

import sys
import time
from .models import AuditClaim, AuditResult, SourceEvidence
from .sources import propublica, usaspending, paperclip
from .formatters import format_narrative

# ONS UK wealth data — static citations (no REST API available)
ONS_WEALTH_DATA = {
    "black_african_median": 34000,
    "white_british_median": 314000,
    "source_url": "https://www.ons.gov.uk/peoplepopulationandcommunity/personalandhouseholdfinances/incomeandwealth/datasets/householdwealthingreatbritainbyethnicity",
    "survey": "Wealth and Assets Survey, April 2016 to March 2018",
    "note": "Figures are median total household wealth in Great Britain.",
}


def audit_claim(claim):
    """Audit a single claim. Returns an AuditResult."""
    dispatch = {
        "nonprofit_funding": _audit_nonprofit,
        "federal_spending": _audit_spending,
        "wealth_gap": _audit_wealth_gap,
        "contractor_link": _audit_contractor_link,
    }
    handler = dispatch.get(claim.claim_type, _audit_unknown)
    return handler(claim)


def audit_batch(claims, progress_callback=None):
    """Audit a list of claims with throttling and progress."""
    results = []
    for i, claim in enumerate(claims):
        result = audit_claim(claim)
        results.append(result)
        if progress_callback:
            progress_callback(i + 1, len(claims), result)
        time.sleep(0.5)  # additional throttle between claims
    return results


def _audit_nonprofit(claim):
    """Audit a nonprofit funding claim via ProPublica 990 data."""
    evidence = []
    discrepancy = None

    for entity in claim.entities:
        orgs = propublica.search_nonprofit(entity)
        if not orgs:
            continue

        # Take the top match
        org = orgs[0]
        ein = org.get("ein")
        if not ein:
            continue

        evidence.append(SourceEvidence(
            api_source="propublica",
            url=f"https://projects.propublica.org/nonprofits/organizations/{ein}",
            raw_field="search_result",
            value_found=org.get("total_revenue"),
            description=f"Found: {org['name']} (EIN: {ein}), {org.get('city', '')}, {org.get('state', '')}. Revenue: ${org.get('total_revenue') or 0:,.0f}",
        ))

        filing = propublica.get_filing(ein)
        if filing and filing.get("filings"):
            latest = filing["filings"][0]
            grants = latest.get("grants_paid")
            evidence.append(SourceEvidence(
                api_source="propublica",
                url=f"https://projects.propublica.org/nonprofits/organizations/{ein}",
                raw_field="latest_filing",
                value_found=latest.get("total_expenses"),
                description=(
                    f"Latest 990 (period {latest.get('tax_period', 'unknown')}): "
                    f"Revenue ${latest.get('total_revenue', 0):,.0f}, "
                    f"Expenses ${latest.get('total_expenses', 0):,.0f}"
                    + (f", Grants ${grants:,.0f}" if grants else "")
                ),
            ))

    if not evidence:
        verdict, confidence = "INSUFFICIENT_DATA", "low"
        discrepancy = "No matching nonprofit found in ProPublica Nonprofit Explorer."
    elif claim.amount_claimed:
        # ProPublica has modern filings only (2001+)
        # Historical claims (pre-2001) won't have direct matches
        verdict = "INSUFFICIENT_DATA"
        confidence = "medium"
        discrepancy = (
            f"Claimed amount: ${claim.amount_claimed:,.0f}. "
            "ProPublica 990 data covers electronic filings (roughly 2001+). "
            "Historical grants from the 1920s-1940s require archival sources: "
            "Rockefeller Archive Center (https://rockarch.org), "
            "National Archives (https://www.archives.gov)."
        )
    else:
        verdict, confidence = "PARTIALLY_SUPPORTED", "medium"

    narrative = format_narrative(claim, verdict, evidence, discrepancy)
    return AuditResult(
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        evidence=tuple(evidence),
        discrepancy=discrepancy,
        ledger_narrative=narrative,
    )


def _audit_spending(claim):
    """Audit a federal spending claim via USAspending.gov."""
    evidence = []
    discrepancy = None

    for entity in claim.entities:
        result = usaspending.total_awarded(entity)
        if result["count"] > 0:
            evidence.append(SourceEvidence(
                api_source="usaspending",
                url=f"https://www.usaspending.gov/search/?hash=recipient-{entity.replace(' ', '+')}",
                raw_field="spending_by_award",
                value_found=result["total"],
                description=(
                    f"{entity}: {result['count']} awards found, "
                    f"total obligated: ${result['total']:,.0f}"
                ),
            ))
            # Include top awards as individual evidence
            for award in result["awards"][:3]:
                if award.get("amount"):
                    evidence.append(SourceEvidence(
                        api_source="usaspending",
                        url=f"https://www.usaspending.gov/award/{award.get('award_id', '')}",
                        raw_field="individual_award",
                        value_found=award["amount"],
                        description=(
                            f"{award.get('description', 'N/A')[:100]} — "
                            f"Agency: {award.get('agency', 'N/A')}"
                        ),
                    ))

    if not evidence:
        verdict, confidence = "INSUFFICIENT_DATA", "low"
    elif claim.amount_claimed:
        total_found = sum(e.value_found for e in evidence if e.raw_field == "spending_by_award" and e.value_found)
        verdict, confidence = _assess_financial_match(claim.amount_claimed, total_found)
        if verdict != "SUPPORTED":
            discrepancy = f"Claimed: ${claim.amount_claimed:,.0f}. Found in USAspending: ${total_found:,.0f}."
    else:
        verdict, confidence = "PARTIALLY_SUPPORTED", "medium"

    narrative = format_narrative(claim, verdict, evidence, discrepancy)
    return AuditResult(
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        evidence=tuple(evidence),
        discrepancy=discrepancy,
        ledger_narrative=narrative,
    )


def _audit_wealth_gap(claim):
    """Audit a wealth gap claim against ONS UK data."""
    evidence = []
    discrepancy = None

    ons = ONS_WEALTH_DATA
    evidence.append(SourceEvidence(
        api_source="ons_uk",
        url=ons["source_url"],
        raw_field="median_total_wealth",
        value_found=ons["black_african_median"],
        description=(
            f"ONS {ons['survey']}: "
            f"Black African median total wealth: £{ons['black_african_median']:,}. "
            f"White British median total wealth: £{ons['white_british_median']:,}."
        ),
    ))

    if claim.amount_claimed:
        # Check if claim matches ONS data
        if abs(claim.amount_claimed - ons["black_african_median"]) < 5000:
            verdict, confidence = "SUPPORTED", "high"
        else:
            verdict, confidence = "PARTIALLY_SUPPORTED", "medium"
            discrepancy = (
                f"Claimed: £{claim.amount_claimed:,.0f}. "
                f"ONS reports: £{ons['black_african_median']:,} (Black African) "
                f"vs £{ons['white_british_median']:,} (White British). "
                f"Figures depend on survey period and methodology."
            )
    else:
        verdict, confidence = "SUPPORTED", "high"

    narrative = format_narrative(claim, verdict, evidence, discrepancy)
    return AuditResult(
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        evidence=tuple(evidence),
        discrepancy=discrepancy,
        ledger_narrative=narrative,
    )


def _audit_contractor_link(claim):
    """Audit a defense contractor link via USAspending + Paperclip DB."""
    evidence = []
    discrepancy = None

    for entity in claim.entities:
        # USAspending: confirm they receive federal money
        spending = usaspending.search_awards(entity, limit=5)
        if spending:
            total = sum(a["amount"] for a in spending if a.get("amount"))
            evidence.append(SourceEvidence(
                api_source="usaspending",
                url=f"https://www.usaspending.gov/search/?hash=recipient-{entity.replace(' ', '+')}",
                raw_field="contract_confirmation",
                value_found=total,
                description=f"{entity} receives federal contracts: {len(spending)} recent awards, ${total:,.0f} total.",
            ))

        # Paperclip DB: find genealogical connections
        try:
            with paperclip.PaperclipReader() as reader:
                lineage = reader.find_contractor_lineage(entity)
                for person in lineage:
                    gen_label = {1: "Paperclip scientist", 2: "2nd generation", 3: "3rd generation"}.get(
                        person.get("generation"), "unknown generation"
                    )
                    evidence.append(SourceEvidence(
                        api_source="paperclip_cube",
                        url="file:///operation_paperclip_genealogy (local DB, public records only)",
                        raw_field=f"match_path:{person.get('match_path', 'unknown')}",
                        description=(
                            f"{person['full_name']} ({gen_label}): "
                            f"{person.get('occupation', 'occupation unknown')}. "
                            f"Match via: {person.get('match_path', 'unknown')}."
                        ),
                    ))
        except Exception as e:
            print(f"[engine] paperclip error: {e}", file=sys.stderr)

    if not evidence:
        verdict, confidence = "INSUFFICIENT_DATA", "low"
    else:
        has_spending = any(e.api_source == "usaspending" for e in evidence)
        has_lineage = any(e.api_source == "paperclip_cube" for e in evidence)
        if has_spending and has_lineage:
            verdict, confidence = "SUPPORTED", "high"
        elif has_spending or has_lineage:
            verdict, confidence = "PARTIALLY_SUPPORTED", "medium"
            discrepancy = (
                "Federal spending confirmed but no genealogical link found."
                if has_spending else
                "Genealogical link found but no federal spending data matched."
            )
        else:
            verdict, confidence = "INSUFFICIENT_DATA", "low"

    narrative = format_narrative(claim, verdict, evidence, discrepancy)
    return AuditResult(
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        evidence=tuple(evidence),
        discrepancy=discrepancy,
        ledger_narrative=narrative,
    )


def _audit_unknown(claim):
    """Fallback for unrecognized claim types."""
    narrative = format_narrative(
        claim, "INSUFFICIENT_DATA", [],
        f"Unknown claim type: {claim.claim_type}. Supported types: nonprofit_funding, federal_spending, wealth_gap, contractor_link."
    )
    return AuditResult(
        claim=claim,
        verdict="INSUFFICIENT_DATA",
        confidence="low",
        discrepancy=f"Unrecognized claim_type: {claim.claim_type}",
        ledger_narrative=narrative,
    )


def _assess_financial_match(claimed, found, tolerance=0.25):
    """Compare claimed vs found amounts. Returns (verdict, confidence)."""
    if found == 0:
        return "INSUFFICIENT_DATA", "low"
    ratio = found / claimed
    if 1 - tolerance <= ratio <= 1 + tolerance:
        return "SUPPORTED", "high"
    elif 0.5 <= ratio <= 2.0:
        return "PARTIALLY_SUPPORTED", "medium"
    else:
        return "DISPUTED", "high"
