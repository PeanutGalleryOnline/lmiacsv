from __future__ import annotations

import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

from lmiacsv.build_noc_tables import (
    audit_canonical,
    bilingual_unit_rows,
    crosswalk_rows,
    mapping_cardinalities,
    structure_rows,
)


def source(
    path: Path, *, version: str, source_id: str, language: str = "en"
) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "source_id": source_id,
        "source_kind": "classification_structure",
        "noc_version": version,
        "noc_release": f"{'NOC' if language == 'en' else 'CNP'} {version}",
        "language": language,
        "page_url": "https://www.statcan.gc.ca/page",
        "download_url": "https://www.statcan.gc.ca/source.csv",
        "source_filename": path.name,
        "expected_unit_groups": 1,
        "text_encoding": "utf-8-sig",
        "sha256": hashlib.sha256(content).hexdigest(),
        "archive_path": str(path),
    }


class NocBuildTests(unittest.TestCase):
    def test_structure_normalizes_unit_group_with_hierarchy_and_teer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "noc.csv"
            path.write_text(
                "Level,Hierarchical structure,Code - NOC 2021 V1.0,Class title,Class definition\n"
                "1,Broad Category,6,Sales and service occupations,Broad definition\n"
                "2,Major Group,62,Sales and service supervisors,Major definition\n"
                "3,Sub-major Group,620,Supervisors,Sub-major definition\n"
                "4,Minor Group,6202,Service supervisors,Minor definition\n"
                "5,Unit Group,62020,Food service supervisors,Unit definition\n",
                encoding="utf-8-sig",
            )

            rows = structure_rows(source(path, version="2021", source_id="noc-2021"))

        self.assertEqual(rows[0]["noc_code"], "62020")
        self.assertEqual(rows[0]["teer_category"], "2")
        self.assertEqual(rows[0]["broad_category_code"], "6")
        self.assertEqual(rows[0]["minor_group_code"], "6202")

    def test_pairs_french_structure_on_codes_and_hierarchy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            english_path = root / "noc-en.csv"
            french_path = root / "noc-fr.csv"
            english_path.write_text(
                "Level,Hierarchical structure,Code,Class title,Class definition\n"
                "1,Broad occupational category,6,Sales and service occupations,Broad\n"
                "2,Major group,63,Service supervisors,Major\n"
                "3,Minor group,632,Chefs and cooks,Minor\n"
                "4,Unit group,6322,Cooks,Definition\n",
                encoding="utf-8-sig",
            )
            french_path.write_text(
                "Niveau,Structure hiérarchique,Code,Titres de classes,Définitions de la classe\n"
                "1,Grande catégorie professionnelle,6,Vente et services,Grande catégorie\n"
                "2,Grand groupe,63,Personnel de supervision,Grand groupe\n"
                "3,Groupe intermédiaire,632,Chefs et cuisiniers,Intermédiaire\n"
                "4,Groupe de base,6322,Cuisiniers/cuisinières,Définition\n",
                encoding="utf-8-sig",
            )
            english = structure_rows(source(english_path, version="2016", source_id="en"))
            french = structure_rows(
                source(french_path, version="2016", source_id="fr", language="fr")
            )
            rows = bilingual_unit_rows(english, french)

        self.assertEqual(rows[0]["title_en"], "Cooks")
        self.assertEqual(rows[0]["title_fr"], "Cuisiniers/cuisinières")
        self.assertEqual(rows[0]["minor_group_title_fr"], "Chefs et cuisiniers")
        self.assertEqual(rows[0]["source_id_en"], "en")
        self.assertEqual(rows[0]["source_id_fr"], "fr")

    def test_crosswalk_preserves_direct_and_composed_relationships(self) -> None:
        units = [
            {
                "noc_version": "2011",
                "noc_code": "6322",
                "noc_release_en": "NOC 2011",
                "noc_release_fr": "CNP 2011",
                "title_en": "Cooks",
                "title_fr": "Cuisiniers/cuisinières",
            },
            {
                "noc_version": "2016",
                "noc_code": "6322",
                "noc_release_en": "NOC 2016 Version 1.3",
                "noc_release_fr": "CNP 2016 version 1.3",
                "title_en": "Cooks",
                "title_fr": "Cuisiniers/cuisinières",
            },
            {
                "noc_version": "2021",
                "noc_code": "63200",
                "noc_release_en": "NOC 2021 Version 1.0",
                "noc_release_fr": "CNP 2021 version 1.0",
                "title_en": "Cooks",
                "title_fr": "Cuisiniers/cuisinières",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            english_path = Path(directory) / "crosswalk-en.csv"
            french_path = Path(directory) / "crosswalk-fr.csv"
            english_path.write_text(
                "NOC 2016 V1.3 Code,NOC 2016 V1.3 Title,GSIM Type of Change,"
                "NOC 2021 V1.0 Code,NOC 2021 V1.0 Title,Notes\n"
                "6322,Cooks,VC1 - Code Change,63200,Cooks,\n",
                encoding="utf-8-sig",
            )
            french_path.write_text(
                "Code CNP 2016 v1.3,Titre de la CNP 2016 v1.3,Type de changement GSIM,"
                "Code CNP 2021 v1.0,Titre de la CNP 2021 v1.0,Notes\n"
                "6322,Cuisiniers/cuisinières,VC1 - Changement de code,63200,"
                "Cuisiniers/cuisinières,\n",
                encoding="utf-8-sig",
            )
            english_source = source(
                english_path, version="2016", source_id="crosswalk-en"
            )
            french_source = source(
                french_path,
                version="2016",
                source_id="crosswalk-fr",
                language="fr",
            )
            english_source["source_kind"] = "correspondence"
            french_source["source_kind"] = "correspondence"
            rows = crosswalk_rows(english_source, french_source, units)

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["source_version"] for row in rows}, {"2011", "2016"})
        self.assertEqual({row["mapping_cardinality"] for row in rows}, {"one_to_one"})
        self.assertEqual(
            {row["is_direct_official_correspondence"] for row in rows},
            {"true", "false"},
        )
        self.assertEqual({row["target_title_fr"] for row in rows}, {"Cuisiniers/cuisinières"})
        self.assertEqual({row["gsim_change_fr"] for row in rows}, {"VC1 - Changement de code"})

    def test_mapping_cardinality_does_not_flatten_one_to_many(self) -> None:
        rows = [
            {"source_version": "2016", "source_code": "1111", "target_code": "11100"},
            {"source_version": "2016", "source_code": "1111", "target_code": "11101"},
        ]

        mapping_cardinalities(rows)

        self.assertEqual([row["mapping_cardinality"] for row in rows], ["one_to_many"] * 2)

    def test_canonical_audit_requires_version_and_code_match(self) -> None:
        units = [
            {"noc_version": "2011", "noc_code": "6322"},
            {"noc_version": "2021", "noc_code": "63200"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canonical.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["noc_version", "noc_code", "quality_flags"],
                )
                writer.writeheader()
                writer.writerow({"noc_version": "2011", "noc_code": "6322", "quality_flags": ""})
                writer.writerow({"noc_version": "2021", "noc_code": "63200", "quality_flags": ""})
            audit = audit_canonical(path, units)

        self.assertEqual(audit["join_status"], "complete")
        self.assertEqual(audit["canonical_record_count"], 2)


if __name__ == "__main__":
    unittest.main()
