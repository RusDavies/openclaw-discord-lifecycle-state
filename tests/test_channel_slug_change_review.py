from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import channel_slug_change_review as slug_review  # noqa: E402


class ChannelSlugChangeReviewTests(unittest.TestCase):
    def test_loads_decision_by_channel_and_current_name(self) -> None:
        path = self.decisions(
            [
                {
                    "channel_id": "1",
                    "current_channel_name": "example",
                    "decision": "preserve-current-slug",
                    "canonical_slug": "example",
                    "reason": "keep current",
                }
            ]
        )

        decisions = slug_review.load_decisions(path)

        self.assertIn(("1", "example"), decisions)
        self.assertEqual(decisions[("1", "example")].canonical_slug, "example")

    def test_row_without_decision_is_unresolved(self) -> None:
        row = slug_review.SlugReviewRow(
            channel_id="1",
            current_channel_name="example",
            proposed_channel_name="🟢-different",
            project_folder="projects/different",
            proposed_state="active",
            decision="",
            canonical_slug="",
            reason="",
            risk_notes=(slug_review.SLUG_CHANGE_RISK,),
        )

        self.assertEqual(row.resolution_status, "unresolved")

    def test_invalid_decision_is_flagged(self) -> None:
        row = slug_review.SlugReviewRow(
            channel_id="1",
            current_channel_name="example",
            proposed_channel_name="🟢-different",
            project_folder="projects/different",
            proposed_state="active",
            decision="preserve-current-slug",
            canonical_slug="",
            reason="",
            risk_notes=(slug_review.SLUG_CHANGE_RISK,),
        )

        self.assertEqual(row.resolution_status, "invalid-decision")

    def test_json_summary_counts_decisions(self) -> None:
        rows = [
            slug_review.SlugReviewRow(
                channel_id="1",
                current_channel_name="example",
                proposed_channel_name="🟢-different",
                project_folder="projects/different",
                proposed_state="active",
                decision="preserve-current-slug",
                canonical_slug="example",
                reason="keep current",
                risk_notes=(slug_review.SLUG_CHANGE_RISK,),
            ),
            slug_review.SlugReviewRow(
                channel_id="2",
                current_channel_name="old",
                proposed_channel_name="🟢-new",
                project_folder="projects/new",
                proposed_state="active",
                decision="exclude-noncanonical-channel",
                canonical_slug="new",
                reason="old source channel",
                risk_notes=(slug_review.SLUG_CHANGE_RISK,),
            ),
        ]

        data = slug_review.json_data(
            rows,
            index_path=PROJECT_ROOT / "index.json",
            category_snapshot_path=None,
            decisions_path=PROJECT_ROOT / "decisions.json",
        )

        self.assertEqual(data["summary"]["slug_change_rows"], 2)
        self.assertEqual(data["summary"]["resolved_rows"], 2)
        self.assertEqual(data["summary"]["unresolved_rows"], 0)
        self.assertEqual(
            data["summary"]["decisions"],
            {
                "exclude-noncanonical-channel": 1,
                "preserve-current-slug": 1,
            },
        )

    def decisions(self, entries: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        )
        self.addCleanup(lambda path=handle.name: Path(path).unlink(missing_ok=True))
        with handle:
            json.dump(
                {
                    "schema": "openclaw.lifecycle.channel_slug_decisions.v1",
                    "decisions": entries,
                },
                handle,
            )
        return Path(handle.name)


if __name__ == "__main__":
    unittest.main()
