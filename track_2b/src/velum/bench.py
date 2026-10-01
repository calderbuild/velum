"""VelumBench: anonymisation test cases built from decisions the courts have already published.

The courts' own placeholders mark what had to be removed. Each placeholder is filled with a
synthetic Swiss identity (consistent per letter), which gives realistic "raw" text with exact
gold spans for free. Judges, clerks and lawyers that the courts publish by name are the gold for
what must stay. No real party is ever re-identified: every inserted identity is invented.
"""

import hashlib
import random
import re

PLACEHOLDER = re.compile(r"(?<![\w.])([A-Z](?:\.[A-Z])*)\.?_{3,}")
LEGAL_FORM_AFTER = re.compile(
    r"\s*(?:AG|SA|GmbH|Sàrl|Sagl|S\.r\.l\.|Srl|S\.A\.|Ltd|Inc|SE|KG|LLC|& Co|Holding|Genossenschaft)\b"
)
ORG_BEFORE = re.compile(
    r"(?i)(?:firma|société|ditta|klinik|clinique|clinica|garage|bank|banque|banca|stiftung|fondation|fondazione|verein|association|associazione|hotel|restaurant|spital|hôpital|ospedale)\s+$"
)
LAWYER_BEFORE = re.compile(
    r"(?:Rechtsanwalt|Rechtsanwältin|Fürsprecher(?:in)?|Advokat(?:in)?|avocat[e]?|Me|Maître|avv\.|avvocat[oa])\s+$"
)
PLACE_BEFORE = re.compile(
    r"(?i)(?:wohnhaft in|mit Sitz in|\bin|Gemeinde|Einwohnergemeinde|Bezirk|Bezirksgericht|Kreisgericht|Regionalgericht|"
    r"Amtsgericht|Stadt|domiciliée?s? à|sise? à|commune de|district de|arrondissement de|ville de|"
    r"domiciliat[oaie] a|con sede a|Comune di|Pretura di|Municipio di)\s+$"
)
FEMALE_AFTER = re.compile(
    r"^.{0,60}?\b(?:Beschwerdeführerin|Klägerin|Gesuchstellerin|Gesuchsgegnerin|Berufungsklägerin|Ehefrau|Mutter|Tochter|"
    r"Schwester|recourante|intimée|requérante|demanderesse|défenderesse|épouse|mère|fille|sœur|domiciliée|née\b|"
    r"moglie|madre|figlia|sorella|domiciliata|nata\b|cittadina)",
    re.S,
)
PERSON_AFTER = re.compile(
    r"^,?\s*(?:Beschwerdeführer|Beschwerdegegner|Kläger|Beklagte|Gesuchsteller|Berufungskläger|Beschuldigte|Angeklagte|geboren|"
    r"vertreten|recourant|intimé|requérant|demandeur|défendeur|né|représenté|ricorrente|opponente|attore|convenuto|nat[oa]|patrocinat)"
)
PERSON_BEFORE = re.compile(
    r"(?:Herr|Frau|M\.|Mme|signor[a]?|Ehemann|Ehefrau|Sohn|Tochter|Vater|Mutter|Kind|fils|fille|père|mère|épou[sx]e?|"
    r"figli[oa]|padre|madre|moglie|marito|Dr\.|med\.)\s+$"
)
FEMALE_BEFORE = re.compile(
    r"(?:Frau|Mme|Madame|signora|sig\.ra|Ehefrau|Mutter|Tochter|épouse|mère|fille|moglie|madre|figlia)\s+$"
)

NAMES = {
    "de": {
        "m": "Hans Peter Thomas Daniel Martin Andreas Markus Stefan Christian Michael Urs Beat Reto Lukas Simon Marco Patrick Roger Bruno Walter Kurt Fritz Jonas Adrian",
        "f": "Anna Maria Ursula Ruth Elisabeth Monika Barbara Sandra Nicole Claudia Daniela Karin Sabine Brigitte Verena Esther Regula Sarah Laura Lea Julia Petra Silvia Corinne",
        "s": "Brunner Baumann Zimmermann Widmer Wyss Suter Baumgartner Bachmann Studer Bühler Kälin Hofer Lüthi Bieri Egli Sutter Schär Wenger Zürcher "
        "Aebischer Ammann Bosshard Hürlimann Imhof Kaufmann Locher Rüegg Stucki Vogel Wälti Zbinden Zollinger Furrer Gisler Kunz Leuenberger "
        "Odermatt Portmann Rohner Schläpfer Tanner Vetsch Waser Zehnder Gubler Hunziker Isler Jenni Kohler Lanz Matter Nyffeler Probst",
        "towns": "8953 Dietikon|8610 Uster|8800 Thalwil|8180 Bülach|8302 Kloten|3600 Thun|3400 Burgdorf|3800 Interlaken|3700 Spiez|4600 Olten|"
        "5400 Baden|5600 Lenzburg|4800 Zofingen|6210 Sursee|6340 Baar|9500 Wil|9200 Gossau|7000 Chur|8280 Kreuzlingen|9100 Herisau|"
        "8840 Einsiedeln|6370 Stans|6060 Sarnen|6460 Altdorf|8750 Glarus|4410 Liestal|4153 Reinach|4310 Rheinfelden|3900 Brig|3930 Visp|"
        "8500 Frauenfeld|5000 Aarau|6300 Zug|8200 Schaffhausen|4500 Solothurn|8640 Rapperswil|8630 Rüti|8340 Hinwil|8620 Wetzikon|5430 Wettingen",
        "streets": "Bahnhofstrasse Hauptstrasse Dorfstrasse Kirchgasse Schulhausstrasse Seestrasse Bergstrasse Industriestrasse Gartenstrasse "
        "Lindenweg Rosenweg Feldstrasse Poststrasse Mühlegasse Sonnenbergstrasse Birkenweg Ahornstrasse Wiesenstrasse",
        "sectors": "Holzbau Treuhand Immobilien Transporte Gartenbau Elektro Haustechnik Bauunternehmung Informatik Reinigungen Metallbau Malerei",
        "brands": "Seeblick Bergsonne Talgarten Sonnenhalde Waldrand Lindenmatt Felsenegg Rosenhügel Seematt Höhenweg",
    },
    "fr": {
        "m": "Jean Pierre Michel Philippe Alain Jacques Christophe Nicolas Laurent Olivier François Stéphane Yves Bernard Claude Julien Sébastien Luc André Thierry Fabien Cédric",
        "f": "Marie Françoise Catherine Nathalie Isabelle Sylvie Christine Martine Sophie Valérie Chantal Anne Monique Céline Camille Julie Sandrine Véronique Aline Mélanie Laurence",
        "s": "Favre Rochat Bonvin Perrin Jaquet Monnier Clerc Chappuis Cuche Ducret Fournier Gachet Girard Jaccard Junod Maillard Marchand Mauron "
        "Mercier Morand Pasche Pittet Rapin Reymond Roulin Sauthier Thévenaz Vuilleumier Zufferey Bourquin Berthoud Cosandey Genoud Guex "
        "Michaud Nicolet Oberson Piguet Savary Tinguely Udry Vionnet Barras Crettenand Fragnière Bersier Dafflon Gremaud Masserey Rossier",
        "towns": "1400 Yverdon-les-Bains|1110 Morges|1820 Montreux|1800 Vevey|1260 Nyon|1530 Payerne|1350 Orbe|1860 Aigle|1630 Bulle|1680 Romont|"
        "1920 Martigny|1870 Monthey|3960 Sierre|2300 La Chaux-de-Fonds|2400 Le Locle|2800 Delémont|2900 Porrentruy|1227 Carouge|1213 Onex|"
        "1290 Versoix|1212 Grand-Lancy|1020 Renens|1009 Pully|1066 Epalinges|1196 Gland|1302 Vufflens-la-Ville|1510 Moudon|1580 Avenches|2520 La Neuveville|2740 Moutier",
        "streets": "Rue de la Gare|Avenue de la Gare|Rue du Lac|Chemin des Vignes|Route de Lausanne|Rue du Midi|Chemin du Bois|Rue de l'Église|"
        "Avenue des Alpes|Rue du Marché|Chemin de la Forêt|Route Cantonale|Chemin des Pâquis|Rue des Moulins",
        "sectors": "Fiduciaire Constructions Garage Immobilière Transports Menuiserie Électricité Informatique Nettoyages Boulangerie Peinture",
        "brands": "Alpéa|Clairval|Beaulac|Montclair|Sylvana|Lumina|Valforte|Rivéa|Solvane|Arbelle",
    },
    "it": {
        "m": "Marco Luca Paolo Giuseppe Giovanni Mario Franco Roberto Stefano Alessandro Fabio Claudio Massimo Sergio Davide Matteo Lorenzo Fabrizio Gianni Renato Carlo Pietro",
        "f": "Maria Anna Giulia Francesca Laura Elena Chiara Paola Silvia Sara Federica Monica Cristina Daniela Roberta Alessandra Valentina Simona Patrizia Lucia Marta",
        "s": "Rossi Ferrari Bianchi Fontana Pedrazzini Lombardi Guidotti Rusconi Galli Sala Bassi Cattaneo Colombo Croce Fumagalli Gianini Grassi "
        "Maggi Mariotta Martinoli Mazzoleni Monti Moretti Pellandini Poretti Quadri Respini Righetti Rigoni Rezzonico Soldati Storni Taddei "
        "Tognola Valsangiacomo Vassalli Zanetti Zappa Beffa Bizzini Canepa Dazio Ferrazzini Gilardi Induni Jelmini Lepori Morosoli Nessi Pagani",
        "towns": "6900 Lugano|6500 Bellinzona|6600 Locarno|6850 Mendrisio|6830 Chiasso|6648 Minusio|6512 Giubiasco|6710 Biasca|6780 Airolo|"
        "6612 Ascona|6982 Agno|6942 Savosa|6616 Losone|6596 Gordola|6834 Morbio Inferiore|6877 Coldrerio|6855 Stabio|6807 Taverne|"
        "6814 Lamone|7742 Poschiavo|6535 Roveredo|6563 Mesocco|6517 Arbedo|6593 Cadenazzo|6862 Rancate",
        "streets": "Via Cantonale|Via San Gottardo|Via della Stazione|Via Lugano|Via Nassa|Via ai Monti|Via Ciseri|Via Motta|Via Vela|Via Pessina|Via Bellinzona|Via Locarno",
        "sectors": "Fiduciaria Costruzioni Garage Immobiliare Trasporti Falegnameria Elettricità Informatica Pulizie Panetteria Pittura",
        "brands": "Aurora|Primavera|Stella|Bellavista|Serena|Girasole|Fiordaliso|Miralago|Solaria|Belvedere",
    },
}

COMPOSITION = re.compile(
    r"(?:Besetzung|Composition|Composizione|Mitwirkend:?)\s*(.{3,700}?)\s*"
    r"(?:Parteien|Verfahrensbeteiligte|Participants|Parties|Parti\b|Partecipanti|Beschluss vom|Urteil vom|Statuant|\*{3,}|in Sachen)",
    re.S,
)
ROLE_WORDS = re.compile(
    r"(?i)\b(?:Bundes(?:verwaltungs|straf)?richter(?:in|innen)?|Ersatz(?:ober)?richter(?:in)?|Ober(?:richter|richterin)|Richter(?:in|innen)?|"
    r"Gerichtsschreiber(?:in)?|Gerichtspräsident(?:in)?|Einzelrichter(?:in)?|Instruktionsrichter(?:in)?|Kammerpräsident(?:in)?|"
    r"Abteilungspräsident(?:in)?|Präsident(?:in)?|Vorsitzende[r]?|Vorsitz|nebenamtliche[r]?|Juges?|fédéra(?:l|ux|le|les)|Président[e]?|"
    r"Greffi(?:er|ère)|suppléant[e]?|unique|giudic[ei]|federal[ei]|president(?:e|essa)|del collegio|cancellier[ea]|in qualità di|"
    r"lic\.|iur\.|phil\.|Dr\.|MLaw|Prof\.|M\.|Mme|MM\.|Mmes|les|la|le|et|und|sowie|e|unico|Ire|IIe|Cour|Abteilung)(?!\w)"
)
LAWYER = re.compile(
    r"(?:vertreten durch|v\.d\.|a\.v\.d\.|représentée?s? par|assistée?s? par|patrocinat[oaie]|rappresentat[oaie])\s+"
    r"(?:(?:Rechtsanwalt|Rechtsanwältin|Fürsprecher(?:in)?|Advokat(?:in)?|Dr\.|lic\.\s?iur\.|MLaw|Prof\.|Me|Maître|dall'|dalla|dal|da|avv\.|avvocat[oa])\s*)*"
    r"([A-ZÄÖÜÉ][\wäöüéèàç'’-]+(?:\s+(?:von|van|de|di|da|del|della)?\s*[A-ZÄÖÜÉ][\wäöüéèàç'’-]+){0,3})"
)
NOT_NAMES = {
    "Inhaberin", "Inhaber", "Rechtsdienst", "Departement", "Direktion", "Amt", "Office", "Ufficio", "Service", "Kanton",
    "Canton", "Cantone", "Mitglied", "Mitglieder", "Zustimmung", "Rechtsanwalt", "Rechtsanwältin", "Fürsprecher",
    "Fürsprecherin", "Advokat", "Advokatin", "Maître", "Avocat", "Avvocato", "Avvocata", "Gerichtsschreiber",
    "Gerichtsschreiberin", "Präsident", "Präsidentin", "Vizepräsident", "Vizepräsidentin", "Ersatzrichter", "Ersatzrichterin",
}


def _pool(language, key):
    raw = NAMES[language][key]
    return raw.split("|") if "|" in raw else raw.split()


def _fresh(rng, pool, taken, text_cf):
    """Pick a value whose words appear nowhere in the source decision and that is not yet used."""
    for _ in range(200):
        v = rng.choice(pool)
        words = re.findall(r"[^\W\d_][\w'’-]*", v)
        if v not in taken and not any(
            re.search(r"(?<!\w)" + re.escape(w.casefold()) + r"(?!\w)", text_cf)
            for w in words
            if len(w) > 2
        ):
            taken.add(v)
            return v
    raise RuntimeError("name pool exhausted")


def classify(text, matches):
    """Decide per placeholder letter whether it stands for a person, company, place or lawyer."""
    kinds = {}
    for key in {m.group(1) for m in matches}:
        own = [m for m in matches if m.group(1) == key]
        before = [text[max(0, m.start() - 40) : m.start()] for m in own]
        after = [text[m.end() : m.end() + 25] for m in own]
        if any(LAWYER_BEFORE.search(b) for b in before):
            kinds[key] = "lawyer"
        elif any(LEGAL_FORM_AFTER.match(a) for a in after) or any(
            ORG_BEFORE.search(b) for b in before
        ):
            kinds[key] = "company"
        elif _is_place(before, after):
            kinds[key] = "place"
        else:
            kinds[key] = "person"
    return kinds


def _is_place(before, after):
    """A strong place cue somewhere, and no occurrence that reads like a person.

    A role word right after a place cue belongs to the party before it
    ("B. AG, mit Sitz in U.,\nBeschwerdegegnerin"), so it is not a person cue there.
    """
    place = [bool(PLACE_BEFORE.search(b)) for b in before]
    person = [
        (not p and bool(PERSON_AFTER.match(a))) or bool(PERSON_BEFORE.search(b))
        for p, a, b in zip(place, after, before)
    ]
    return any(place) and not any(person)


def keep_names(text):
    """Judges, clerks and lawyers the court publishes by name: the gold for what must stay."""
    names = {}
    m = COMPOSITION.search(text[:4000])
    if m:
        block = ROLE_WORDS.sub(" ", PLACEHOLDER.sub(" ", m.group(1)))
        for piece in re.split(r"[,;:()\n/.]|\s{2,}|\s(?:et|und|e)\s", block):
            words = [w for w in piece.split() if w[:1].isupper() and len(w) > 2]
            if 1 <= len(words) <= 4 and not set(words) & NOT_NAMES:
                names[" ".join(words)] = "court_official"
    for m in LAWYER.finditer(text):
        name = m.group(1)
        if not set(name.split()) & NOT_NAMES and not PLACEHOLDER.search(name):
            names.setdefault(name, "lawyer")
    return names


def generate(row):
    """Fill one published decision with synthetic identities. Returns a VelumBench test case or None."""
    published, lang = row["full_text"], row["language"]
    matches = list(PLACEHOLDER.finditer(published))
    if not matches or lang not in NAMES:
        return None
    rng = random.Random(row["decision_id"])
    kinds, cf = classify(published, matches), published.casefold()
    taken, identity = set(), {}
    for key in sorted(
        kinds, key=lambda k: min(m.start() for m in matches if m.group(1) == k)
    ):
        identity[key] = _identity(
            kinds[key], key, published, matches, lang, rng, taken, cf
        )
    out, gold, pos, seen, address_done = [], [], 0, set(), False
    header_end = published.find("\n", 1500) % (len(published) + 1)
    for m in matches:
        key, kind = m.group(1), kinds[m.group(1)]
        out.append(published[pos : m.start()])
        start = sum(map(len, out))
        if (
            kind == "lawyer"
        ):  # this court anonymises lawyers; leave its placeholder alone
            out.append(m.group(0))
        else:
            ident = identity[key]
            value = (
                ident["full"]
                if key not in seen or kind != "person" or rng.random() < 0.4
                else ident["short"]
            )
            out.append(value + (" " if published[m.end() : m.end() + 1].isalnum() else ""))
            gold.append(
                {
                    "start": start,
                    "end": start + len(value),
                    "text": value,
                    "entity": key,
                    "kind": kind,
                }
            )
            seen.add(key)
            if (
                not address_done
                and kind in ("person", "company")
                and m.end() < header_end
                and re.match(r",\s*\n", published[m.end() :])
            ):
                address = f"{ident['street']}, {ident['town']}"
                a = start + len(value) + 2
                out.append(", " + address)
                gold.append(
                    {
                        "start": a,
                        "end": a + len(address),
                        "text": address,
                        "entity": key + "#address",
                        "kind": "address",
                    }
                )
                address_done = True
        pos = m.end()
    out.append(published[pos:])
    text = "".join(out)
    for g in gold:
        assert text[g["start"] : g["end"]] == g["text"], g
    keep = [
        {
            "text": n,
            "kind": k,
            "count": len(re.findall(r"(?<!\w)" + re.escape(n) + r"(?!\w)", text)),
        }
        for n, k in keep_names(published).items()
    ]
    return {
        "id": row["decision_id"],
        "court": row["court"],
        "language": lang,
        "docket": row["docket_number"],
        "decision_date": row["decision_date"],
        "legal_area": row.get("legal_area") or "",
        "source_url": row["source_url"],
        "text": text,
        "gold": gold,
        "keep": [k for k in keep if k["count"]],
        "published_text": published,
        "license": "Decision text: not protected by copyright (Art. 5 para. 1 let. c URG). Synthetic identities: CDLA-Permissive-2.0.",
        "provenance": row["provenance"],
    }


def _identity(kind, key, text, matches, lang, rng, taken, cf):
    own = [m for m in matches if m.group(1) == key]
    # Addresses are scored by span coverage only, so street and town need not be unique.
    town = rng.choice(_pool(lang, "towns"))
    street = f"{rng.choice(_pool(lang, 'streets'))} {rng.randint(1, 120)}"
    if kind == "place":
        name = _fresh(
            rng, [t.split(" ", 1)[1] for t in _pool(lang, "towns")], taken, cf
        )
        return {"full": name, "short": name, "street": street, "town": town}
    if kind == "company":
        before = [text[max(0, m.start() - 40) : m.start()] for m in own]
        if any(ORG_BEFORE.search(b) for b in before):
            name = _fresh(rng, _pool(lang, "brands"), taken, cf)
        else:
            surname, sector = (
                _fresh(rng, _pool(lang, "s"), taken, cf),
                rng.choice(_pool(lang, "sectors")),
            )
            name = f"{surname} {sector}" if lang == "de" else f"{sector} {surname}"
        return {"full": name, "short": name, "street": street, "town": town}
    female = any(
        FEMALE_AFTER.match(text[m.end() : m.end() + 80])
        or FEMALE_BEFORE.search(text[max(0, m.start() - 25) : m.start()])
        for m in own
    )
    given, surname = (
        _fresh(rng, _pool(lang, "f" if female else "m"), taken, cf),
        _fresh(rng, _pool(lang, "s"), taken, cf),
    )
    return {
        "full": f"{given} {surname}",
        "short": surname,
        "street": street,
        "town": town,
        "gender": "f" if female else "m",
    }


def split_of(case_id):
    """About one case in seven goes to dev (prompt work); the rest is the held-out test split."""
    return (
        "dev"
        if int(hashlib.sha256(case_id.encode()).hexdigest(), 16) % 7 == 0
        else "test"
    )


# --- scoring ---------------------------------------------------------------------------------


def _covered(span, edits):
    """Characters of the span that no edit covers (whitespace and punctuation ignored)."""
    left = [c.isalnum() for c in span["text"]]
    for e in edits:
        lo, hi = max(span["start"], e["start"]), min(span["end"], e["end"])
        for i in range(lo, hi):
            left[i - span["start"]] = False
    return not any(left)


def score(case, output, edits):
    """Leaks, over-redaction and consistency for one system output on one case."""
    gold = case["gold"]
    protected = [g for g in gold if _covered(g, edits)]
    labels = {}
    for g in protected:
        reps = {
            e["replacement"]
            for e in edits
            if e["start"] < g["end"] and e["end"] > g["start"]
        }
        labels.setdefault(g["entity"], set()).update(reps)
    pseudo = {k: v for k, v in labels.items() if not k.endswith("#address")}
    multi = [k for k in pseudo if sum(1 for g in protected if g["entity"] == k) > 1]
    consistent = sum(1 for k in multi if len(pseudo[k]) == 1)
    firsts = [next(iter(v)) for v in pseudo.values() if len(v) == 1]
    keep_in = sum(k["count"] for k in case["keep"])
    keep_out = sum(
        min(
            k["count"],
            len(re.findall(r"(?<!\w)" + re.escape(k["text"]) + r"(?!\w)", output)),
        )
        for k in case["keep"]
    )
    gold_chars = (
        set().union(*(range(g["start"], g["end"]) for g in gold)) if gold else set()
    )
    extra = sum(
        1
        for e in edits
        for i in range(e["start"], e["end"])
        if i not in gold_chars and case["text"][i].isalnum()
    )
    return {
        "gold": len(gold),
        "leaked": len(gold) - len(protected),
        "leaked_by_kind": _count(g["kind"] for g in gold if g not in protected),
        "gold_by_kind": _count(g["kind"] for g in gold),
        "keep": keep_in,
        "keep_redacted": keep_in - keep_out,
        "multi": len(multi),
        "consistent": consistent,
        "label_collisions": len(firsts) - len(set(firsts)),
        "extra_chars": extra,
        "chars": len(case["text"]),
    }


MARKER = re.compile(r"[A-Z]{1,2}\.(?:_{3,})?|\[…\]")


def free_form(case, edits):
    """Edits outside the gold spans that write anything other than a placeholder or a removal
    marker: rewording, deleted passages, changed numbers. Velum cannot produce them."""
    gold = set().union(*(range(g["start"], g["end"]) for g in case["gold"]))
    return [
        e
        for e in edits
        if not MARKER.fullmatch(e["replacement"].strip())
        and any(c.isalnum() for c in case["text"][e["start"] : e["end"]] + e["replacement"])
        and not gold.intersection(range(e["start"], e["end"]))
    ]


def _count(items):
    out = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


def aggregate(scores):
    tot = {
        k: sum(s[k] for s in scores)
        for k in (
            "gold",
            "leaked",
            "keep",
            "keep_redacted",
            "multi",
            "consistent",
            "label_collisions",
            "extra_chars",
            "chars",
        )
    }
    by_kind = {}
    for s in scores:
        for k, n in s["gold_by_kind"].items():
            by_kind.setdefault(k, [0, 0])[0] += n
        for k, n in s["leaked_by_kind"].items():
            by_kind[k][1] += n
    return {
        "cases": len(scores),
        "recall": 1 - tot["leaked"] / max(1, tot["gold"]),
        "zero_leak_cases": sum(1 for s in scores if s["leaked"] == 0)
        / max(1, len(scores)),
        "over_redaction": tot["keep_redacted"] / max(1, tot["keep"]),
        "consistency": tot["consistent"] / max(1, tot["multi"]),
        "label_collisions": tot["label_collisions"],
        "extra_chars_per_1k": 1000 * tot["extra_chars"] / max(1, tot["chars"]),
        "recall_by_kind": {
            k: 1 - leaked / total for k, (total, leaked) in sorted(by_kind.items())
        },
        "gold_mentions": tot["gold"],
        "keep_mentions": tot["keep"],
    }
