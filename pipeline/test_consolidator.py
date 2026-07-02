"""
pipeline/test_consolidator.py — Testes do módulo de consolidação de aparições.
"""

import unittest
from decimal import Decimal

from pipeline.consolidator import (
    ConsolidationResult,
    _gap_seconds,
    _merge,
    _parse_ts,
    consolidate_project_appearances,
)

TENANT  = "tenant-1"
PROJECT = "project-1"


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_app(
    appearance_id: str,
    camera_id: str,
    species: str,
    ts_start: str,
    ts_end: str,
    species_score: float,
    support_frames: int = 1,
    individual_count: int = 1,
    best_crop: str | None = None,
    tenant_id: str = TENANT,
    project_id: str = PROJECT,
    video_id: str = "video-1",
) -> dict:
    if best_crop is None:
        best_crop = f"frames/{appearance_id}.jpg"
    return {
        "tenant_id":               tenant_id,
        "project_id":              project_id,
        "video_id":                video_id,
        "appearance_id":           appearance_id,
        "video_id#appearance_id":  f"{video_id}#{appearance_id}",
        "tenant_id#project_id":    f"{tenant_id}#{project_id}",
        "species#appearance_id":   f"{species}#{appearance_id}",
        "camera_id":               camera_id,
        "species":                 species,
        "ts_start":                ts_start,
        "ts_end":                  ts_end,
        "support_frames":          support_frames,
        "best_crop_s3_key":        best_crop,
        "species_score":           Decimal(str(species_score)),
        "individual_count":        individual_count,
        "review_status":           "pending",
        "taxonomic_level":         "species",
        "taxonomic_path":          "mammalia",
        "model_version":           "speciesnet-v5.0.5",
    }


class MockTable:
    """Tabela DynamoDB em memória para testes."""

    def __init__(self, items: list[dict]) -> None:
        self._store = {i["video_id#appearance_id"]: dict(i) for i in items}
        self.updates: list[tuple] = []
        self.deletes: list[str]  = []

    def query(self, **kwargs) -> dict:
        return {"Items": list(self._store.values())}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues, **kwargs):
        sk   = Key["video_id#appearance_id"]
        item = self._store[sk]
        field_map = {
            ":te": "ts_end",
            ":sf": "support_frames",
            ":bc": "best_crop_s3_key",
            ":ic": "individual_count",
            ":ss": "species_score",
        }
        for alias, val in ExpressionAttributeValues.items():
            if alias in field_map:
                item[field_map[alias]] = val
        self.updates.append((sk, dict(ExpressionAttributeValues)))

    def delete_item(self, Key, **kwargs):
        sk = Key["video_id#appearance_id"]
        self._store.pop(sk, None)
        self.deletes.append(sk)

    @property
    def items(self) -> list[dict]:
        return list(self._store.values())


# ── Testes de helpers ──────────────────────────────────────────────────────────

class TestParseTs(unittest.TestCase):
    def test_iso_basic(self):
        dt = _parse_ts("2025-01-11T08:14:30")
        self.assertEqual(dt.hour, 8)
        self.assertEqual(dt.minute, 14)

    def test_none_input(self):
        self.assertIsNone(_parse_ts(None))

    def test_empty_string(self):
        self.assertIsNone(_parse_ts(""))

    def test_invalid(self):
        self.assertIsNone(_parse_ts("not-a-date"))


class TestGapSeconds(unittest.TestCase):
    def test_150_seconds(self):
        gap = _gap_seconds("2025-01-11T08:00:30", "2025-01-11T08:03:00")
        self.assertAlmostEqual(gap, 150.0)

    def test_negative_gap(self):
        # ts_start anterior a ts_end — gap negativo
        gap = _gap_seconds("2025-01-11T08:05:00", "2025-01-11T08:00:00")
        self.assertAlmostEqual(gap, -300.0)

    def test_none_if_missing(self):
        self.assertIsNone(_gap_seconds(None, "2025-01-11T08:00:00"))
        self.assertIsNone(_gap_seconds("2025-01-11T08:00:00", None))


class TestMerge(unittest.TestCase):
    def _make_pair(self, score_a=0.75, score_b=0.95):
        a = make_app("A", "0004", "dasyprocta leporina",
                     "2025-01-11T08:00:00", "2025-01-11T08:00:30",
                     species_score=score_a, support_frames=3, individual_count=1,
                     best_crop="crop_A.jpg")
        b = make_app("B", "0004", "dasyprocta leporina",
                     "2025-01-11T08:03:00", "2025-01-11T08:03:30",
                     species_score=score_b, support_frames=5, individual_count=2,
                     best_crop="crop_B.jpg")
        return a, b

    def test_ts_range(self):
        a, b = self._make_pair()
        m = _merge(a, b)
        self.assertEqual(m["ts_start"], "2025-01-11T08:00:00")
        self.assertEqual(m["ts_end"],   "2025-01-11T08:03:30")

    def test_support_frames_sum(self):
        a, b = self._make_pair()
        m = _merge(a, b)
        self.assertEqual(m["support_frames"], 8)

    def test_individual_count_max(self):
        a, b = self._make_pair()
        m = _merge(a, b)
        self.assertEqual(m["individual_count"], 2)

    def test_best_crop_b_wins(self):
        a, b = self._make_pair(score_a=0.75, score_b=0.95)
        m = _merge(a, b)
        self.assertEqual(m["best_crop_s3_key"], "crop_B.jpg")

    def test_best_crop_a_wins(self):
        a, b = self._make_pair(score_a=0.98, score_b=0.70)
        m = _merge(a, b)
        self.assertEqual(m["best_crop_s3_key"], "crop_A.jpg")

    def test_survivor_keeps_appearance_id(self):
        a, b = self._make_pair()
        m = _merge(a, b)
        self.assertEqual(m["appearance_id"], "A")
        self.assertEqual(m["video_id#appearance_id"], "video-1#A")


# ── Testes de consolidação ─────────────────────────────────────────────────────

class TestConsolidateGapWithinThreshold(unittest.TestCase):
    """Gap = 150s < 300s → deve consolidar."""

    def setUp(self):
        self.a = make_app("A", "0004", "dasyprocta leporina",
                          "2025-01-11T08:00:00", "2025-01-11T08:00:30",
                          species_score=0.80, support_frames=3, video_id="v1")
        self.b = make_app("B", "0004", "dasyprocta leporina",
                          "2025-01-11T08:03:00", "2025-01-11T08:03:30",
                          species_score=0.90, support_frames=4, video_id="v2")
        self.table = MockTable([self.a, self.b])

    def test_result_counts(self):
        result = consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertEqual(result.merged, 1)
        self.assertEqual(result.deleted, 1)
        self.assertEqual(result.appearances_before, 2)
        self.assertEqual(result.appearances_after, 1)

    def test_victim_deleted(self):
        consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertIn("v2#B", self.table.deletes)
        self.assertNotIn("v1#A", self.table.deletes)

    def test_survivor_updated(self):
        consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertEqual(len(self.table.updates), 1)
        sk, vals = self.table.updates[0]
        self.assertEqual(sk, "v1#A")
        self.assertEqual(vals[":te"], "2025-01-11T08:03:30")
        self.assertEqual(int(vals[":sf"]), 7)   # 3 + 4

    def test_best_crop_from_b(self):
        consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        survivor = self.table._store.get("v1#A")
        self.assertEqual(survivor["best_crop_s3_key"], "frames/B.jpg")


class TestConsolidateGapOutsideThreshold(unittest.TestCase):
    """Gap = 570s > 300s → deve manter separadas."""

    def setUp(self):
        a = make_app("A", "0004", "dasyprocta leporina",
                     "2025-01-11T08:00:00", "2025-01-11T08:00:30",
                     species_score=0.80, video_id="v1")
        b = make_app("B", "0004", "dasyprocta leporina",
                     "2025-01-11T08:10:00", "2025-01-11T08:10:30",
                     species_score=0.90, video_id="v2")
        self.table = MockTable([a, b])

    def test_no_consolidation(self):
        result = consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertEqual(result.merged, 0)
        self.assertEqual(result.deleted, 0)
        self.assertEqual(result.appearances_after, 2)

    def test_no_deletes_or_updates(self):
        consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertEqual(self.table.deletes, [])
        self.assertEqual(self.table.updates, [])


class TestConsolidateDifferentSpeciesSameCamera(unittest.TestCase):
    """Espécies diferentes na mesma câmera → não consolida."""

    def setUp(self):
        a = make_app("A", "0004", "dasyprocta leporina",
                     "2025-01-11T08:00:00", "2025-01-11T08:00:30",
                     species_score=0.80, video_id="v1")
        b = make_app("B", "0004", "puma concolor",
                     "2025-01-11T08:02:00", "2025-01-11T08:02:30",
                     species_score=0.99, video_id="v1")
        self.table = MockTable([a, b])

    def test_no_consolidation(self):
        result = consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertEqual(result.merged, 0)
        self.assertEqual(result.deleted, 0)

    def test_both_survive(self):
        consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertEqual(len(self.table.items), 2)


class TestConsolidateDifferentCamerasSameSpecies(unittest.TestCase):
    """Câmeras diferentes → não consolida mesmo com gap pequeno."""

    def setUp(self):
        a = make_app("A", "0004", "dasyprocta leporina",
                     "2025-01-11T08:00:00", "2025-01-11T08:00:30",
                     species_score=0.80, video_id="v1")
        b = make_app("B", "0005", "dasyprocta leporina",
                     "2025-01-11T08:01:00", "2025-01-11T08:01:30",
                     species_score=0.90, video_id="v2")
        self.table = MockTable([a, b])

    def test_no_consolidation(self):
        result = consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertEqual(result.merged, 0)
        self.assertEqual(result.deleted, 0)

    def test_both_survive(self):
        consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertEqual(len(self.table.items), 2)


class TestConsolidateBestCropSelection(unittest.TestCase):
    """best_crop_s3_key deve ser o frame com maior species_score."""

    def _run(self, score_a, score_b, crop_a, crop_b) -> dict:
        a = make_app("A", "0004", "species-x",
                     "2025-01-11T08:00:00", "2025-01-11T08:00:30",
                     species_score=score_a, best_crop=crop_a, video_id="v1")
        b = make_app("B", "0004", "species-x",
                     "2025-01-11T08:02:00", "2025-01-11T08:02:30",
                     species_score=score_b, best_crop=crop_b, video_id="v2")
        table = MockTable([a, b])
        consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=table)
        return table._store.get("v1#A", {})

    def test_b_has_higher_score(self):
        survivor = self._run(0.70, 0.95, "crop_A.jpg", "crop_B.jpg")
        self.assertEqual(survivor["best_crop_s3_key"], "crop_B.jpg")

    def test_a_has_higher_score(self):
        survivor = self._run(0.98, 0.60, "crop_A.jpg", "crop_B.jpg")
        self.assertEqual(survivor["best_crop_s3_key"], "crop_A.jpg")

    def test_equal_scores_keeps_a(self):
        survivor = self._run(0.90, 0.90, "crop_A.jpg", "crop_B.jpg")
        self.assertEqual(survivor["best_crop_s3_key"], "crop_A.jpg")


class TestConsolidateMissingTsSkipped(unittest.TestCase):
    """Aparições sem ts_start/ts_end devem ser ignoradas (não consolidadas nem deletadas)."""

    def setUp(self):
        a = make_app("A", "0004", "dasyprocta leporina",
                     "2025-01-11T08:00:00", "2025-01-11T08:00:30",
                     species_score=0.80, video_id="v1")
        b = make_app("B", "0004", "dasyprocta leporina",
                     "2025-01-11T08:02:00", "2025-01-11T08:02:30",
                     species_score=0.90, video_id="v2")
        # C sem timestamps
        c = make_app("C", "0004", "dasyprocta leporina",
                     None, None,
                     species_score=0.95, video_id="v3")
        c["ts_start"] = None
        c["ts_end"]   = None
        self.table = MockTable([a, b, c])

    def test_c_never_deleted(self):
        consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertNotIn("v3#C", self.table.deletes)

    def test_a_b_merged_c_survives(self):
        result = consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertEqual(result.merged, 1)
        self.assertEqual(result.deleted, 1)
        # C conta no before/after mas não é deletada
        self.assertEqual(result.appearances_before, 3)
        self.assertEqual(result.appearances_after, 2)


class TestConsolidateChained(unittest.TestCase):
    """A → B → C com gaps ≤ threshold → consolida em cadeia, restando só A."""

    def setUp(self):
        # A: 08:00–08:00:30, B: 08:03–08:03:30, C: 08:06–08:06:30 (gaps=150s cada)
        self.a = make_app("A", "0004", "species-x",
                          "2025-01-11T08:00:00", "2025-01-11T08:00:30",
                          species_score=0.70, support_frames=2, video_id="v1")
        self.b = make_app("B", "0004", "species-x",
                          "2025-01-11T08:03:00", "2025-01-11T08:03:30",
                          species_score=0.85, support_frames=3, video_id="v2")
        self.c = make_app("C", "0004", "species-x",
                          "2025-01-11T08:06:00", "2025-01-11T08:06:30",
                          species_score=0.80, support_frames=4, video_id="v3")
        self.table = MockTable([self.a, self.b, self.c])

    def test_result_counts(self):
        result = consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertEqual(result.merged, 2)
        self.assertEqual(result.deleted, 2)
        self.assertEqual(result.appearances_before, 3)
        self.assertEqual(result.appearances_after, 1)

    def test_only_a_survives(self):
        consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        self.assertIn("v2#B", self.table.deletes)
        self.assertIn("v3#C", self.table.deletes)
        self.assertEqual(len(self.table.items), 1)

    def test_support_frames_total(self):
        consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        survivor = self.table._store.get("v1#A")
        self.assertEqual(int(survivor["support_frames"]), 9)  # 2+3+4

    def test_best_crop_from_b(self):
        # B tem o maior score (0.85)
        consolidate_project_appearances(TENANT, PROJECT, gap_seconds=300, table=self.table)
        survivor = self.table._store.get("v1#A")
        self.assertEqual(survivor["best_crop_s3_key"], "frames/B.jpg")


class TestConsolidateEmptyProject(unittest.TestCase):
    """Projeto sem aparições → retorna zeros sem erros."""

    def test_empty(self):
        table = MockTable([])
        result = consolidate_project_appearances(TENANT, PROJECT, table=table)
        self.assertEqual(result.merged, 0)
        self.assertEqual(result.deleted, 0)
        self.assertEqual(result.appearances_before, 0)
        self.assertEqual(result.appearances_after, 0)


class TestConsolidateSingleAppearance(unittest.TestCase):
    """Uma única aparição → nada a consolidar."""

    def test_single(self):
        a = make_app("A", "0004", "species-x",
                     "2025-01-11T08:00:00", "2025-01-11T08:00:30",
                     species_score=0.80)
        table = MockTable([a])
        result = consolidate_project_appearances(TENANT, PROJECT, table=table)
        self.assertEqual(result.merged, 0)
        self.assertEqual(result.appearances_after, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
