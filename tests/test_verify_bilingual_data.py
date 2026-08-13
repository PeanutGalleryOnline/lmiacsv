from __future__ import annotations

import unittest
from collections import Counter
from types import SimpleNamespace

from lmiacsv.verify_bilingual_data import counter_examples, employer_pair_status


def parsed(
    exact: Counter,
    core: Counter,
    measures: Counter,
    totals: dict[str, int],
) -> SimpleNamespace:
    return SimpleNamespace(exact=exact, core=core, measures=measures, totals=totals)


class BilingualVerifierTests(unittest.TestCase):
    def test_status_preserves_each_reconciliation_layer(self) -> None:
        totals = {"record_count": 1, "position_count": 2, "lmia_count": 1}
        en = parsed(Counter({("en",): 1}), Counter({("core",): 1}), Counter({("m",): 1}), totals)
        exact = parsed(Counter({("en",): 1}), en.core, en.measures, totals)
        core = parsed(Counter({("fr",): 1}), en.core, en.measures, totals)
        measure = parsed(
            Counter({("fr",): 1}), Counter({("other",): 1}), en.measures, totals
        )
        summary = parsed(
            Counter({("fr",): 1}),
            Counter({("other",): 1}),
            Counter({("other",): 1}),
            totals,
        )
        mismatch = parsed(
            summary.exact,
            summary.core,
            summary.measures,
            {**totals, "position_count": 3},
        )

        self.assertEqual("normalized_record_match", employer_pair_status(en, exact))
        self.assertEqual("language_neutral_core_match", employer_pair_status(en, core))
        self.assertEqual("measure_distribution_match", employer_pair_status(en, measure))
        self.assertEqual("summary_totals_only_match", employer_pair_status(en, summary))
        self.assertEqual("summary_totals_mismatch", employer_pair_status(en, mismatch))

    def test_counter_examples_preserve_multiplicity(self) -> None:
        left = Counter({("ON", "high_wage"): 3})
        right = Counter({("ON", "high_wage"): 1})

        examples = counter_examples(left, right, ("province", "stream"))

        self.assertEqual(
            [{"province": "ON", "stream": "high_wage", "multiplicity": 2}],
            examples,
        )


if __name__ == "__main__":
    unittest.main()
