"""Validate the preparation contract and canonical synthetic case; no model calls."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(case, contract, provenance):
    require(case["origin"] == "synthetic", "case must be synthetic")
    require(case["case_id"] == "CASE-SYN-104", "canonical case changed")
    require(case["invoice_id"] == "INV-SYN-4817", "canonical invoice changed")
    require(case["tenant"] == "northstar-retail", "canonical tenant changed")
    units = case["organizations"]["northstar-retail"]["business_units"]
    require(set(units) == {"service-operations", "inventory-operations"}, "unit mapping changed")
    require(case["organizations"]["northstar-retail"]["support_function"] == "platform-engineering", "support mapping changed")
    require(case["organizations"]["harbor-retail"]["relationship"] == "separate_tenant", "Harbor boundary changed")
    purchase = case["purchase"]
    require((purchase["description"], purchase["quantity"], purchase["unit_price_minor"], purchase["currency"]) == ("blue mug", 2, 1250, "GBP"), "canonical purchase changed")
    require(purchase["verification_status"] == "requires_check", "purchase check cannot be inferred complete")
    report = case["customer_report"]
    require((report["description"], report["quantity"], report["evidence_type"]) == ("one red mug", 1, "reported_claim"), "report is not verified fulfillment")
    require(case["fulfillment"] == {"status": "unknown", "source_id": None}, "fulfillment must remain unknown")
    policy = case["policy"]
    require(policy["policy_id"] == "returns-v3" and policy["origin"] == "synthetic", "baseline policy changed")
    require(set(policy["required_checks"]) == {"purchase", "case"}, "required checks changed")
    require(policy["automatic_refund_authorized"] is False, "automatic refund cannot be authorized")
    require(case["policy_v4"] == {"activation": "explicit_branch_or_reset_only", "active": False}, "v4 cannot silently replace v3")
    chapters = contract["chapters"]
    require(contract["implemented"] is True, "approved provisional CLI must match the implemented spine")
    require([c["chapter"] for c in chapters] == list(range(1, 15)), "fourteen sequential chapters required")
    require(len({c["slug"] for c in chapters}) == 14, "duplicate chapter slug")
    stages = [s for c in chapters for s in c["stages"]]
    require(len(stages) == len(set(stages)), "duplicate stage command")
    for chapter in chapters:
        require(all(0 < n < chapter["chapter"] for n in chapter["needs"]), "chapter prerequisite is not earlier")
    require(provenance["synthetic_fixture"]["derived_from_uci_rows"] is False, "synthetic case must not be UCI-derived")
    data = provenance["public_dataset"]
    require(data["doi"] == "10.24432/C5BW33" and data["license"] == "CC-BY-4.0", "public data attribution changed")
    require(data["status"] == "not_downloaded_for_this_project" and data["archive_sha256"] is None and data["workbook_sha256"] is None and data["derived_records"] == [], "baseline cannot claim unobserved data processing")


def load_inputs():
    return [json.loads((ROOT / p).read_text()) for p in [
        "fixtures/case-syn-104.json", "contracts/chapters.json",
        "data/provenance.json",
    ]]


if __name__ == "__main__":
    validate(*load_inputs())
    print("BASELINE_OK chapters=14 fixture=CASE-SYN-104")
