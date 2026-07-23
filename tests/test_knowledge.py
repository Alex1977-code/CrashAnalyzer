"""Wissensbasis: Bugcheck-Codes und Empfehlungskatalog."""
from src import knowledge


def test_lookup_known_code_liefert_deutschen_klartext():
    info = knowledge.bugcheck_info(0x133)
    assert info["name"] == "DPC_WATCHDOG_VIOLATION"
    assert info["hex"] == "0x00000133"
    assert "Treiber" in info["klartext"]
    assert info["rec_ids"]
    assert info["fallback"] is False


def test_lookup_unbekannter_code_faellt_generisch_zurueck():
    info = knowledge.bugcheck_info(0xDEADBEEF)
    assert info["fallback"] is True
    assert info["name"] == "UNBEKANNTER_STOPCODE"
    assert info["rec_ids"], "auch unbekannte Codes brauchen Empfehlungen"


def test_alle_rec_ids_aus_bugchecks_existieren_im_katalog():
    katalog = {r["id"] for r in knowledge.recommendations()}
    for code, entry in knowledge.all_bugchecks().items():
        for rid in entry["rec_ids"]:
            assert rid in katalog, f"Code {code}: unbekannte rec_id {rid}"


def test_alle_kind_rec_ids_existieren_im_katalog():
    katalog = {r["id"] for r in knowledge.recommendations()}
    for kind, rids in knowledge.KIND_RECS.items():
        assert rids, f"kind {kind} ohne Empfehlungen"
        for rid in rids:
            assert rid in katalog, f"kind {kind}: unbekannte rec_id {rid}"


def test_empfehlungen_vollstaendig_und_gestuft():
    recs = knowledge.recommendations()
    assert len(recs) >= 12
    for r in recs:
        assert r["title"] and r["text"], r["id"]
        assert r["category"] in ("sofort", "diagnose", "hardware", "profi"), r["id"]
        assert 1 <= r["priority"] <= 4, r["id"]
        assert "tool_id" in r  # None erlaubt, Schluessel Pflicht
