"""Tests for the refactored indexer pipeline node."""
import sys
from unittest.mock import MagicMock, AsyncMock, patch
import os

import pytest

# Mock Firebase and Qdrant modules before any src.services imports
for mod in [
    "src.firebase_service",
    "src.vector_store_helper",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()


# ===== _parse_env_overrides =====


class TestParseEnvOverrides:
    def _parse(self, settings, env_vars=None):
        """Helper that patches env vars and calls _parse_env_overrides."""
        from src.services.data_pipeline.indexer import _parse_env_overrides

        env = env_vars or {}
        with patch.dict(os.environ, env, clear=False):
            # Clean up any leftover env vars from previous tests
            for key in [
                "INDEX_SKIP_MANIFESTOS", "INDEX_SKIP_CANDIDATES",
                "INDEX_SKIP_PROFESSIONS", "CLASSIFY_THEMES",
                "MAX_CONCURRENT_INDEX", "MAX_PAGES_PER_CANDIDATE",
            ]:
                if key not in env:
                    os.environ.pop(key, None)
            return _parse_env_overrides(settings)

    def test_defaults(self):
        settings = {"classify_themes": True, "index_manifestos": True, "max_pages_per_candidate": 10}
        result = self._parse(settings)
        assert result is True  # classify_themes
        assert settings["index_manifestos"] is True  # not overridden

    def test_skip_manifestos(self):
        settings = {"index_manifestos": True, "max_pages_per_candidate": 10}
        self._parse(settings, {"INDEX_SKIP_MANIFESTOS": "true"})
        assert settings["index_manifestos"] is False

    def test_skip_candidates(self):
        settings = {"index_candidates": True, "max_pages_per_candidate": 10}
        self._parse(settings, {"INDEX_SKIP_CANDIDATES": "1"})
        assert settings["index_candidates"] is False

    def test_skip_professions(self):
        settings = {"index_professions": True, "max_pages_per_candidate": 10}
        self._parse(settings, {"INDEX_SKIP_PROFESSIONS": "yes"})
        assert settings["index_professions"] is False

    def test_disable_classify_themes(self):
        settings = {"classify_themes": True, "max_pages_per_candidate": 10}
        result = self._parse(settings, {"CLASSIFY_THEMES": "false"})
        assert result is False

    def test_max_concurrent_index(self):
        settings = {"max_pages_per_candidate": 10}
        self._parse(settings, {"MAX_CONCURRENT_INDEX": "8"})
        assert settings["max_concurrent_index"] == 8

    def test_max_pages_per_candidate(self):
        settings = {"max_pages_per_candidate": 10}
        with patch.dict(os.environ, {"MAX_PAGES_PER_CANDIDATE": "20"}, clear=False):
            from src.services.data_pipeline.indexer import _parse_env_overrides
            _parse_env_overrides(settings)
            assert settings["max_pages_per_candidate"] == 20
            assert os.environ["MAX_PAGES_PER_CANDIDATE"] == "20"

    def test_case_insensitive_yes_values(self):
        settings = {"index_manifestos": True, "max_pages_per_candidate": 10}
        self._parse(settings, {"INDEX_SKIP_MANIFESTOS": "YES"})
        assert settings["index_manifestos"] is False

    def test_non_truthy_value_does_not_skip(self):
        settings = {"index_manifestos": True, "max_pages_per_candidate": 10}
        self._parse(settings, {"INDEX_SKIP_MANIFESTOS": "false"})
        assert settings["index_manifestos"] is True


# ===== PhaseTracker =====


class TestPhaseTracker:
    @pytest.mark.asyncio
    async def test_start_and_finish_phase(self):
        from src.services.data_pipeline.indexer.progress import PhaseTracker

        with patch("src.services.data_pipeline.indexer.progress.update_status", new_callable=AsyncMock) as mock_update:
            tracker = PhaseTracker("test_node")
            await tracker.start_phase("manifestos")
            assert tracker.phase_status["manifestos"] == "running"

            await tracker.finish_phase("manifestos")
            assert tracker.phase_status["manifestos"] == "done"

            # Should have emitted status updates
            assert mock_update.call_count >= 2

    @pytest.mark.asyncio
    async def test_error_phase(self):
        from src.services.data_pipeline.indexer.progress import PhaseTracker

        with patch("src.services.data_pipeline.indexer.progress.update_status", new_callable=AsyncMock):
            tracker = PhaseTracker("test_node")
            await tracker.error_phase("candidates")
            assert tracker.phase_status["candidates"] == "error"

    @pytest.mark.asyncio
    async def test_progress_update(self):
        from src.services.data_pipeline.indexer.progress import PhaseTracker

        with patch("src.services.data_pipeline.indexer.progress.update_status", new_callable=AsyncMock) as mock_update:
            tracker = PhaseTracker("test_node")
            tracker.update_progress("candidates", {"done": 5, "total": 10})
            await tracker.emit()

            # Check merged data was passed
            call_kwargs = mock_update.call_args
            counts = call_kwargs.kwargs.get("counts", {})
            assert counts["candidates_done"] == 5
            assert counts["candidates_total"] == 10

    @pytest.mark.asyncio
    async def test_multi_phase_merge(self):
        from src.services.data_pipeline.indexer.progress import PhaseTracker

        with patch("src.services.data_pipeline.indexer.progress.update_status", new_callable=AsyncMock) as mock_update:
            tracker = PhaseTracker("test_node")
            tracker.phase_status["manifestos"] = "done"
            tracker.phase_status["candidates"] = "running"
            tracker.update_progress("manifestos", {"chunks": 100})
            tracker.update_progress("candidates", {"done": 3, "total": 20})

            await tracker.emit()

            counts = mock_update.call_args.kwargs.get("counts", {})
            assert counts["active_phases"] == "candidates"
            assert counts["completed_phases"] == "manifestos"
            assert counts["manifestos_chunks"] == 100
            assert counts["candidates_done"] == 3


# ===== Manifesto phase =====


class TestManifestoPhase:
    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        from src.services.data_pipeline.base import NodeConfig
        from src.services.data_pipeline.indexer.manifesto_phase import run_manifesto_phase
        from src.services.data_pipeline.indexer.progress import PhaseTracker

        cfg = NodeConfig(
            node_id="indexer", label="test",
            settings={"index_manifestos": False},
        )
        with patch("src.services.data_pipeline.indexer.progress.update_status", new_callable=AsyncMock):
            tracker = PhaseTracker("indexer")
            result = await run_manifesto_phase(cfg, tracker)
        assert result == 0

    @pytest.mark.asyncio
    async def test_skips_when_already_indexed(self):
        from src.services.data_pipeline.base import NodeConfig
        from src.services.data_pipeline.indexer.manifesto_phase import run_manifesto_phase
        from src.services.data_pipeline.indexer.progress import PhaseTracker

        cfg = NodeConfig(
            node_id="indexer", label="test",
            settings={"index_manifestos": True},
            checkpoints={"manifesto_indexed_parties": {"lr": 50}},
        )
        with patch("src.services.data_pipeline.indexer.progress.update_status", new_callable=AsyncMock):
            tracker = PhaseTracker("indexer")
            result = await run_manifesto_phase(cfg, tracker, force=False)
        assert result == 0

    @pytest.mark.asyncio
    async def test_force_overrides_checkpoint(self):
        from src.services.data_pipeline.base import NodeConfig
        from src.services.data_pipeline.indexer.manifesto_phase import run_manifesto_phase
        from src.services.data_pipeline.indexer.progress import PhaseTracker

        cfg = NodeConfig(
            node_id="indexer", label="test",
            settings={"index_manifestos": True},
            checkpoints={"manifesto_indexed_parties": {"lr": 50}},
        )
        with patch("src.services.data_pipeline.indexer.progress.update_status", new_callable=AsyncMock):
            tracker = PhaseTracker("indexer")
            with patch(
                "src.services.manifesto_indexer.index_all_parties",
                new_callable=AsyncMock,
                return_value={"lr": 30, "rn": 20},
            ):
                result = await run_manifesto_phase(cfg, tracker, force=True)

        assert result == 50  # 30 + 20
        assert cfg.checkpoints["manifesto_indexed_parties"] == {"lr": 30, "rn": 20}


# ===== Profession phase =====


class TestProfessionPhase:
    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        from src.services.data_pipeline.base import NodeConfig
        from src.services.data_pipeline.indexer.profession_phase import run_profession_phase
        from src.services.data_pipeline.indexer.progress import PhaseTracker

        cfg = NodeConfig(
            node_id="indexer", label="test",
            settings={"index_professions": False},
        )
        with patch("src.services.data_pipeline.indexer.progress.update_status", new_callable=AsyncMock):
            tracker = PhaseTracker("indexer")
            result = await run_profession_phase(cfg, tracker)
        assert result == 0
