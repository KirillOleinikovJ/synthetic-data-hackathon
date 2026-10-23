"""Build data/service_catalog.json from the official GOÄ ophthalmology section."""

from __future__ import annotations

import json
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "reference" / "goae_augen_raw.txt"
OUT = ROOT / "data" / "service_catalog.json"
PUNKTWERT = Decimal("0.0582873")

GENERAL = [
    (1, "Beratung, auch mittels Fernsprecher", "consult", False),
    (5, "Symptombezogene Untersuchung", "consult", False),
    (6, "Vollstaendige Untersuchung eines Organsystems, alle Augenabschnitte", "consult", False),
    (34, "Eroerterung mind. 20 Minuten, einschliesslich Planung einer Operation", "preop", False),
    (200, "Verband, ausgenommen Schnell- und Spruehverbaende", "followup", False),
    (2007, "Entfernung von Faeden oder Klammern", "followup", False),
    (440, "Zuschlag fuer Operationsmikroskop bei ambulanter Operation", "surcharge", False),
    (491, "Infiltrationsanaesthesie grosser Bezirke", "surgery", True),
]

SURCHARGES = [
    (442, 400, 250, 499, "Zuschlag ambulante Operation, 250 bis 499 Punkte"),
    (443, 750, 500, 799, "Zuschlag ambulante Operation, 500 bis 799 Punkte"),
    (444, 1300, 800, 1199, "Zuschlag ambulante Operation, 800 bis 1199 Punkte"),
    (445, 2200, 1200, 99999, "Zuschlag ambulante Operation, 1200 und mehr Punkte"),
]

# id, label, exam codes, surgery codes, bilateral
DIAGNOSES = [
    ("refractive_error", "Refraktionsfehler", ["1200", "1201", "1202"], [], False),
    ("contact_lens", "Kontaktlinsenanpassung", ["1211"], [], False),
    ("strabismus_exam", "Heterophorie oder Strabismus, Diagnostik", ["1216", "1217"], [], False),
    ("strabismus_surgery", "Strabismus, operative Korrektur", ["1216"], ["1330"], False),
    ("visual_field", "Gesichtsfeldausfall", ["1225", "1227"], [], False),
    ("color_vision", "Farbsinnstoerung", ["1228", "1229"], [], False),
    ("night_vision", "Stoerung des Daemmerungssehens", ["1234", "1235"], [], False),
    ("retinal_function", "Netzhautfunktionsstoerung", ["1237"], [], False),
    ("anterior_segment", "Erkrankung des vorderen Augenabschnitts", ["1240", "1252"], [], False),
    ("fundus", "Erkrankung des Augenhintergrunds", ["1242", "1253"], [], False),
    ("retinal_angiography", "Vaskulaere Netzhauterkrankung", ["1249"], [], False),
    ("glaucoma", "Glaukom", ["1241", "1256", "1227"], [], False),
    ("glaucoma_laser", "Glaukom, Lasertrabekuloplastik", ["1256", "1241"], ["1360"], False),
    ("glaucoma_surgery", "Glaukom, filtrierende Operation", ["1256"], ["1382"], False),
    ("dry_eye", "Trockenes Auge", ["1209", "1240"], [], False),
    ("corneal_foreign_body", "Hornhautfremdkörper", ["1240"], ["1276"], False),
    ("intraocular_foreign_body", "Intraokularer Fremdkörper", ["1250"], ["1280"], False),
    ("lid_tumor", "Lidtumor", ["1240"], ["1282"], False),
    ("orbital_fracture", "Orbitafraktur", ["1244"], ["1291"], False),
    ("lacrimal_stenosis", "Traenenwegstenose", ["1293"], ["1300"], False),
    ("dermatochalasis_bds", "Dermatochalasis bds. Oberlid", ["1240"], ["1311"], True),
    ("entropium", "Entropium oder Ektropium", ["1240"], ["1304"], False),
    ("ptosis_bds", "Ptosis bds. Oberlid", ["1240"], ["1306"], True),
    ("pterygium", "Pterygium", ["1240"], ["1321"], False),
    ("corneal_wound", "Perforierende Hornhautverletzung", ["1240"], ["1326"], False),
    ("keratoplasty", "Hornhauttransplantation", ["1204", "1240"], ["1346"], False),
    ("cataract", "Cataracta", ["1242", "1256"], ["1375"], False),
    ("aftercataract", "Nachstar", ["1240"], ["1355"], False),
    ("retinal_detachment", "Netzhautabloesung", ["1242", "1251"], ["1367"], False),
    ("retinal_laser", "Netzhautblutung, Lichtkoagulation", ["1242"], ["1365"], False),
    ("enucleation", "Entfernung des Augapfels", ["1242"], ["1370"], False),
    ("vitrectomy", "Glaskoerpererkrankung", ["1242"], ["1383"], False),
    ("iris_tumor", "Iristumor", ["1240"], ["1380"], False),
    ("amblyopia", "Schwachsichtigkeit", ["1216", "1268"], [], False),
    ("corneal_ulcer", "Hornhautulkus", ["1240"], ["1340"], False),
]


def euro(points: int) -> float:
    amount = (Decimal(points) * PUNKTWERT).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(amount)


def shorten(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text[:180]


def main() -> None:
    raw = RAW.read_text(encoding="utf-8")
    found = re.findall(r"^\| (\d+) \| ([^|]+) \| (\d+) \|", raw, flags=re.M)
    eye = {code: shorten(desc) for code, desc, _points in found}
    eye_points = {code: int(points) for code, _desc, points in found}
    surgery_codes = {code for row in DIAGNOSES for code in row[3]}

    services = []
    for code, desc, phase, bilateral in GENERAL:
        points = {1: 80, 5: 80, 6: 100, 34: 300, 200: 45, 2007: 40, 440: 400, 491: 121}[code]
        factor = 1.0 if code == 440 else 2.3
        services.append(
            {
                "code": str(code),
                "points": points,
                "description": desc,
                "einfachsatz_eur": euro(points),
                "typical_factor": factor,
                "max_factor": factor if code == 440 else 3.5,
                "phase": phase,
                "bilateral_qty": bilateral,
            }
        )
    for code, points, low, high, desc in SURCHARGES:
        services.append(
            {
                "code": str(code),
                "points": points,
                "description": desc,
                "einfachsatz_eur": euro(points),
                "typical_factor": 1.0,
                "max_factor": 1.0,
                "phase": "ambulatory_surcharge",
                "point_min": low,
                "point_max": high,
                "bilateral_qty": False,
            }
        )
    for code in sorted(eye, key=int):
        services.append(
            {
                "code": code,
                "points": eye_points[code],
                "description": eye[code],
                "einfachsatz_eur": euro(eye_points[code]),
                "typical_factor": 2.3,
                "max_factor": 3.5,
                "phase": "surgery" if code in surgery_codes else "exam",
                "bilateral_qty": code in {"1306", "1311"},
            }
        )

    catalog = {
        "_meta": {
            "scenario_id": "goae_ophthalmology_v1",
            "currency": "EUR",
            "billing_rule": "GOAE Stand 01.01.2002",
            "punktwert_eur": "0.0582873",
            "source": "GOÄ Anlage, Abschnitt Augenheilkunde, Nummern 1200-1386, plus allgemeine Leistungen 1, 5, 6, 34, 200, 440, 442-445, 491, 2007.",
            "specialty": "Augenheilkunde",
            "coverage": "Every fee code in GOÄ section I is listed. Diagnoses are groups across that section, not the full ICD catalogue.",
        },
        "diagnoses": [
            {
                "id": row[0],
                "label": row[1],
                "exam_codes": row[2],
                "surgery_codes": row[3],
                "bilateral": row[4],
            }
            for row in DIAGNOSES
        ],
        "services": services,
        "materials": [
            {"description": "OP-Set", "unit_price_eur": 16.66, "max_qty": 1, "priced_by": "sample_invoice_not_goae"},
            {"description": "Vicryl-Naht 6-0", "unit_price_eur": 8.21, "max_qty": 1, "priced_by": "sample_invoice_not_goae"},
            {"description": "Steri-Set", "unit_price_eur": 38.53, "max_qty": 1, "priced_by": "sample_invoice_not_goae"},
        ],
    }
    OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"services {len(services)} diagnoses {len(DIAGNOSES)} -> {OUT}")


if __name__ == "__main__":
    main()
