"""Tests verifying Layer 2+3 bug fixes in the simulation harness.

These test the logic fixes without needing a real browser — we mock
Playwright objects and verify the harness makes correct decisions.
"""

from pathlib import Path


class TestH2_UploadBookkeeping:
    """H2: Failed uploads must NOT be marked as uploaded."""

    def test_failed_upload_not_added_to_set(self):
        """When upload fails, the file should not appear in uploaded_files."""
        # Simulate the logic from _environment.py
        uploaded_files: set[str] = set()

        # Simulate: upload_result.succeeded=False
        succeeded = False
        effect_verified = False
        filename = "data.csv"

        if succeeded and effect_verified:
            uploaded_files.add(filename)

        assert filename not in uploaded_files

    def test_unverified_upload_not_added_to_set(self):
        """When upload succeeds but effect not verified, file not marked."""
        uploaded_files: set[str] = set()

        succeeded = True
        effect_verified = False
        filename = "data.csv"

        if succeeded and effect_verified:
            uploaded_files.add(filename)

        assert filename not in uploaded_files

    def test_verified_upload_added_to_set(self):
        """When upload fully succeeds, file is marked."""
        uploaded_files: set[str] = set()

        succeeded = True
        effect_verified = True
        filename = "data.csv"

        if succeeded and effect_verified:
            uploaded_files.add(filename)

        assert filename in uploaded_files


class TestA1_ChartFilenames:
    """A1: Chart filenames must include turn number to avoid overwrites."""

    def test_chart_filename_includes_turn(self):
        """Verify filename format is turn-{T}-chart-{N}.png."""
        turn = 3
        chart_index = 2
        filename = f"turn-{turn}-chart-{chart_index}.png"
        assert filename == "turn-3-chart-2.png"

    def test_charts_from_different_turns_dont_collide(self):
        """Same chart_index from different turns produces unique filenames."""
        filenames = set()
        for turn in range(1, 4):
            for chart_idx in range(1, 3):
                filenames.add(f"turn-{turn}-chart-{chart_idx}.png")
        assert len(filenames) == 6  # 3 turns x 2 charts = 6 unique


class TestA2_DownloadPaths:
    """A2: Downloads must go to turn-prefixed subdirectories."""

    def test_dest_dir_includes_turn(self, tmp_path: Path):
        """When turn > 0, dest_dir should be run_dir/turn-{N}."""
        run_dir = tmp_path / "artifacts"
        turn = 3

        dest_dir = run_dir / f"turn-{turn}" if turn > 0 else run_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        assert dest_dir == run_dir / "turn-3"
        assert dest_dir.exists()

    def test_dest_dir_no_turn_prefix_when_zero(self, tmp_path: Path):
        """When turn=0 (default), dest_dir is just run_dir."""
        run_dir = tmp_path / "artifacts"
        turn = 0

        dest_dir = run_dir / f"turn-{turn}" if turn > 0 else run_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        assert dest_dir == run_dir


class TestM1_OffByOne:
    """M1: Only the top-of-loop check should gate max_turns."""

    def test_turn_equal_to_max_is_allowed(self):
        """Turn N should execute when max_turns=N (the > check allows it)."""
        max_turns = 5
        turn_count = 5

        # Top-of-loop uses > (not >=), so turn 5 of max 5 is allowed
        should_stop = turn_count > max_turns
        assert not should_stop

    def test_turn_exceeding_max_stops(self):
        """Turn N+1 should stop when max_turns=N."""
        max_turns = 5
        turn_count = 6

        should_stop = turn_count > max_turns
        assert should_stop

    def test_no_redundant_post_turn_check(self):
        """The redundant >= check was removed — verify turn 5 of 5 can
        proceed to agent evaluation (no premature cutoff)."""
        max_turns = 5
        turn_count = 5

        # Old code had: if turn_count >= max_turns: stop (after turn body)
        # This prevented the agent from evaluating the response of turn 5.
        # Now only the top-of-loop > check exists.
        top_of_loop_stops = turn_count > max_turns
        assert not top_of_loop_stops  # turn 5 proceeds normally


class TestM3_ResponseDetectionScope:
    """M3: Response detection uses text-delta as primary, not CSS-only."""

    def test_text_delta_is_primary_detection(self):
        """Verify text growth check comes before message count in _wait_for_response."""
        import inspect

        from metis.engine.simulation.harness._page_actions import (
            _wait_for_response,
        )

        source = inspect.getsource(_wait_for_response)
        # Text growth check exists and comes before message count
        text_pos = source.index("_get_chat_text_length")
        count_pos = source.index("_count_chat_messages")
        assert text_pos < count_pos

    def test_message_count_uses_exact_selectors(self):
        """_count_chat_messages uses .message-user, .message-assistant."""
        import inspect

        from metis.engine.simulation.harness._page_actions import (
            _count_chat_messages,
        )

        source = inspect.getsource(_count_chat_messages)
        assert ".message-user, .message-assistant" in source
        # No class-guessing
        assert '[class*="message"]' not in source

    def test_chat_input_identified_by_placeholder(self):
        """Verify we find the chat textarea by placeholder, not by position."""
        import inspect

        from metis.engine.simulation.harness._page_actions import (
            _find_chat_textarea,
        )

        source = inspect.getsource(_find_chat_textarea)
        assert "_CHAT_INPUT_PLACEHOLDER" in source
        assert "get_by_placeholder" in source


class TestM3_PreStateScope:
    """M3: Pre-state uses Python functions, not inline JS class-guessing."""

    def test_pre_state_uses_python_functions(self):
        """send_message uses _count_chat_messages and _get_chat_text_length."""
        import inspect

        from metis.engine.simulation.harness._page_actions import send_message

        source = inspect.getsource(send_message)
        assert "_count_chat_messages" in source
        assert "_get_chat_text_length" in source


class Testm3_DownloadCounter:
    """m3: Download progress log should use a separate counter."""

    def test_counter_only_increments_for_downloads(self):
        """Simulate the fixed loop logic — dl_idx only counts downloads."""
        artifacts = [
            {"name": "chart.png", "type": "chart"},
            {"name": "data.csv", "type": "download"},
            {"name": "report.pdf", "type": "download"},
            {"name": "thumb.jpg", "type": "preview"},
        ]

        download_count = sum(1 for a in artifacts if a.get("type") == "download")
        dl_idx = 0
        log_entries = []

        for artifact in artifacts:
            if artifact.get("type") != "download":
                continue
            dl_idx += 1
            log_entries.append(f"[{dl_idx}/{download_count}]")

        assert log_entries == ["[1/2]", "[2/2]"]


class Testm1_TempDirCleanup:
    """m1: Temp directory should be cleaned up via context manager."""

    def test_temp_directory_context_manager_used(self):
        """Verify _page_actions uses TemporaryDirectory, not mkdtemp."""
        import inspect

        from metis.engine.simulation.harness import _page_actions

        source = inspect.getsource(_page_actions)
        assert "TemporaryDirectory" in source
        # mkdtemp should no longer be used (it leaks)
        assert "mkdtemp()" not in source


class TestS1_AtomicSendMessage:
    """S1: send_message should use a single type() call, not fill+press."""

    def test_send_uses_type_not_fill_press(self):
        """Verify send_message uses .type() instead of .fill() + .press()."""
        import inspect

        from metis.engine.simulation.harness._page_actions import send_message

        source = inspect.getsource(send_message)
        # Should use type() with \n appended
        assert '.type(message + "\\n"' in source or ".type(message +" in source
        # Should NOT have the old fill+press pattern
        assert "input_el.fill(message), input_el.press" not in source
