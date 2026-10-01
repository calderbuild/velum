"""Checks for the deterministic parts (no model needed): python -m unittest test_velum"""

import unittest

from velum import bench
from velum.anonymize import apply, decide, load_pack, verify_untouched
from velum.detect import Mention, pattern_mentions, plausible, titled, typed, verified

TEXT = """Besetzung
Bundesrichter Raselli, Präsident,
Gerichtsschreiber Füllemann.
Parteien
Hans Brunner, Bahnhofstrasse 12, 8953 Dietikon,
Beschwerdeführer, vertreten durch Rechtsanwalt Daniel Staffelbach,
gegen
Brunner Holzbau AG, mit Sitz in Dietikon,
Gesundheitsdirektion des Kantons Zürich, Obstgartenstrasse 21, 8090 Zürich,
Gegenstand
Beschwerde gegen den Entscheid des Bezirksgerichts Dietikon.
Brunner machte geltend, die Brunner Holzbau AG schulde ihm Lohn. Brunners Einwand ist unbegründet.
"""

MENTIONS = [
    Mention("Raselli", "court_official", "judge", "apertus"),
    Mention("Füllemann", "court_official", "clerk", "apertus"),
    Mention("Hans Brunner", "private_person", "Beschwerdeführer", "apertus"),
    Mention("Daniel Staffelbach", "lawyer", "lawyer", "apertus"),
    Mention("Brunner Holzbau AG", "private_company", "Beschwerdegegnerin", "apertus"),
    Mention("Dietikon", "residence", "", "apertus"),
    Mention("Dietikon", "place", "", "apertus"),
    Mention("Gesundheitsdirektion des Kantons Zürich", "authority", "", "apertus"),
    Mention("Brunner", "private_person", "Beschwerdeführer", "apertus"),
]


class Pipeline(unittest.TestCase):
    def run_pack(self, pack_id):
        pack = load_pack(pack_id)
        entities, edits = decide(TEXT, MENTIONS + pattern_mentions(TEXT), pack)
        return apply(TEXT, entities, edits)

    def test_bger_rules(self):
        out, log = self.run_pack("bger-2020")
        self.assertNotIn("Hans", out)
        self.assertNotIn("Brunner", out)  # full name, surname alone and genitive
        self.assertNotIn(
            "Dietikon", out
        )  # residence, also inside the court name (Art. 7 Abs. 1)
        self.assertNotIn("Bahnhofstrasse", out)  # party address (Art. 7 Abs. 3)
        self.assertIn(
            "Obstgartenstrasse 21, 8090 Zürich", out
        )  # authority address is kept
        for kept in (
            "Raselli",
            "Füllemann",
            "Daniel Staffelbach",
            "Gesundheitsdirektion des Kantons Zürich",
        ):
            self.assertIn(kept, out)
        self.assertIn("B.________ AG", out)  # company placeholder keeps its legal form
        self.assertIn("Bezirksgerichts U.________", out)  # places get letters from U on
        person = {e["replacement"] for e in log if e["type"] == "private_person"}
        self.assertEqual(person, {"A.________"})  # one entity, one placeholder
        self.assertTrue(all(e["basis"] for e in log))  # every edit cites its article

    def test_zurich_rules_differ(self):
        out, _ = self.run_pack("zh-entscheide-2025")
        self.assertNotIn("Staffelbach", out)  # lawyers are anonymised under A.I.4
        self.assertIn("A.,", out)

    def test_address_follows_its_owner(self):
        text = "Gemeinde Dietikon, Bremgartnerstrasse 22, 8953 Dietikon,\nBeschwerdegegnerin.\n"
        mentions = [Mention("Gemeinde Dietikon", "public_body", "Beschwerdegegnerin", "apertus")]
        for pack_id, kept in (("bger-2020", True), ("zh-entscheide-2025", False)):
            entities, edits = decide(text, mentions + pattern_mentions(text), load_pack(pack_id))
            out, _ = apply(text, entities, edits)
            self.assertEqual("Bremgartnerstrasse 22" in out, kept, pack_id)

    def test_guard_catches_changes(self):
        out, log = self.run_pack("bger-2020")
        with self.assertRaises(AssertionError):
            verify_untouched(TEXT, out.replace("Gegenstand", "Gegenstände"), log)

    def test_verified_mentions(self):
        text = "Les docteurs Laurent Vuilleumier et Cédric Bersier. Dupont et Fils SA."
        self.assertEqual(
            verified(
                "docteurs Laurent Vuilleumier et Cédric Bersier", "private_person", text
            ),
            ["Laurent Vuilleumier", "Cédric Bersier"],
        )
        self.assertEqual(
            verified("Dupont et Fils", "private_company", text), ["Dupont et Fils"]
        )
        self.assertEqual(verified("Jean Inventé", "private_person", text), [])

    def test_model_slips_are_corrected(self):
        self.assertEqual(typed("private_person", "court_clerk", "Füllemann"), "court_official")
        self.assertEqual(typed("private_person", "lawyer of the appellant", "Peter Muster"), "lawyer")
        self.assertEqual(typed("private_person", "Beschwerdeführer", "Hans Brunner"), "private_person")
        self.assertEqual(typed("court_official", "court", "Ire Cour de droit public"), "authority")
        for surface, type_ in [
            ("Beschwerdeführerin", "private_person"),
            ("Vater des Beschwerdeführers", "private_person"),
            ("1C_68/2014", "private_company"),
            ("Art. 59 StGB", "identifier"),
        ]:
            self.assertFalse(plausible(surface, type_), surface)
        self.assertTrue(plausible("756.1234.5678.97", "identifier"))
        self.assertTrue(plausible("Federazione Vassalli", "private_company"))

    def test_titled_names_are_not_swept(self):
        text = "1. Bank B., vertreten durch Rechtsanwalt Dr. Andrea-Franco Stöhr,\nHans Brunner, Beschwerdeführer, et Me Xavier de Haller"
        self.assertTrue(titled(text, "Andrea-Franco Stöhr"))
        self.assertTrue(titled(text, "Xavier de Haller"))
        self.assertFalse(titled(text, "Hans Brunner"))


class Bench(unittest.TestCase):
    ROW = {
        "decision_id": "t1",
        "court": "bger",
        "language": "de",
        "docket_number": "1A_1/2020",
        "decision_date": "2020-01-01",
        "legal_area": "",
        "source_url": "",
        "provenance": {},
        "full_text": "Besetzung\nBundesrichter Chaix, Präsident,\nGerichtsschreiber Dold.\nParteien\nA.________,\n"
        "Beschwerdeführer,\nvertreten durch Rechtsanwalt Peter Muster,\ngegen\nB.________ AG, mit Sitz in U.________,\n"
        "Beschwerdegegnerin.\nA.________ wohnt in U.________ und klagte gegen die B.________ AG.",
    }

    def test_generate_and_score(self):
        case = bench.generate(self.ROW)
        kinds = sorted({g["kind"] for g in case["gold"]})
        self.assertEqual(kinds, ["address", "company", "person", "place"])
        self.assertEqual(
            {k["text"] for k in case["keep"]}, {"Chaix", "Dold", "Peter Muster"}
        )
        perfect = [
            {"start": g["start"], "end": g["end"], "replacement": "X"}
            for g in case["gold"]
        ]
        s = bench.score(case, case["text"], perfect)
        self.assertEqual(s["leaked"], 0)
        none = bench.score(case, case["text"], [])
        self.assertEqual(none["leaked"], len(case["gold"]))

    def test_free_form_counts_only_rewording_outside_gold(self):
        case = {"text": "A met Hans Muster on 3 May.", "gold": [{"start": 6, "end": 17}]}
        edits = [
            {"start": 6, "end": 17, "replacement": "anybody"},  # on gold: not counted
            {"start": 0, "end": 1, "replacement": "B.________"},  # placeholder: not counted
            {"start": 21, "end": 22, "replacement": "4"},  # changed date: counted
        ]
        self.assertEqual(bench.free_form(case, edits), [edits[2]])


if __name__ == "__main__":
    unittest.main()
