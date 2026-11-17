"""Exact v0.5 acceptance evidence declarations."""

from __future__ import annotations


def _nodes(path: str, *names: str) -> tuple[str, ...]:
    return tuple(f"{path}::{name}" for name in names) if names else (path,)


_U = "tests/unit/quantide"
_E = "tests/e2e"
_V05_EVIDENCE: dict[str, tuple[str, ...]] = {
    "AC-5001": _nodes(
        f"{_U}/factors/test_plugins.py",
        "test_discovers_valid_plugin_and_source_hash",
        "test_registry_merges_plugin_into_feature_panel",
        "test_default_backtest_params_follow_strategy_interval",
    ),
    "AC-5002": _nodes(
        f"{_U}/factors/test_plugins.py",
        "test_bad_files_are_isolated_with_structured_reasons",
        "test_discovery_isolates_system_exit",
        "test_discovery_enforces_import_timeout",
        "test_source_checkout_directory_is_rejected",
    )
    + _nodes(
        f"{_U}/service/test_factor_study_tasks.py",
        "test_rss_budget_allows_healthy_polars_with_large_virtual_mapping",
        "test_bare_spawn_helper_does_not_import_tests_or_pandas",
    ),
    "AC-5003": _nodes(
        f"{_U}/factors/test_plugins.py",
        "test_source_change_invalidates_cache_and_hash",
    )
    + _nodes(
        f"{_U}/service/test_factor_audit_badge.py",
        "test_unverified_then_pass_then_stale_on_source_change",
        "test_data_signature_tracks_minute_and_pit_dependency_revisions",
    )
    + _nodes(
        f"{_U}/service/test_tracking_universe_contract.py",
        "test_tracking_source_identity_detects_auxiliary_file_revision",
    ),
    "AC-5004": _nodes(
        f"{_U}/audit/test_plugin_audit.py",
        "test_good_plugin_passes_wind_tunnel",
        "test_warmup_window_must_be_null",
        "test_contract_rejects_non_finite_values",
    )
    + _nodes(
        f"{_U}/service/test_factor_wind_tunnel.py",
        "test_monthly_hfq_ohlc_uses_each_day_adjustment_and_month_end_availability",
        "test_monthly_partial_month_is_filtered_per_security",
    )
    + _nodes(
        f"{_U}/service/test_monthly_wind_provenance.py",
        "test_public_monthly_check_compares_bases_from_same_full_months",
        "test_supplied_daily_source_must_reproduce_the_monthly_frame",
    ),
    "AC-5005": _nodes(
        f"{_U}/audit/test_plugin_audit.py",
        "test_missing_over_asset_fails_cross_section_isolation",
        "test_future_shift_fails_future_invariance",
        "test_stateful_global_cache_cannot_hide_future_dependency",
        "test_source_less_plugin_cannot_claim_cold_warm_evidence",
    ),
    "AC-5006": _nodes(
        f"{_U}/factors/test_orthogonality.py",
        "test_high_collinearity_and_top_peer",
        "test_missing_peer_does_not_pollute_other_correlations",
        "test_unknown_factor_column_is_rejected",
    )
    + _nodes(
        f"{_U}/service/test_monthly_wind_provenance.py",
        "test_explicit_monthly_frame_does_not_borrow_unrelated_local_daily_data",
        "test_public_monthly_check_compares_bases_from_same_full_months",
    )
    + _nodes(
        f"{_U}/factors/test_factor_research.py",
        "test_ic_ties_and_t_status",
        "test_equal_day_and_common_endpoints",
    ),
    "AC-5007": _nodes(
        f"{_U}/service/test_v05_factor_presets.py",
        "test_preset_rejects_missing_factor",
        "test_preset_rejects_wind_tunnel_fail",
        "test_validate_preset_rejects_strategy_interval_mismatch",
        "test_preset_roundtrip_keeps_stable_hash_and_atomic_payload",
    ),
    "AC-5008": _nodes(
        f"{_U}/service/test_v05_factor_presets.py",
        "test_ablation_locks_all_shared_conditions",
        "test_shap_summary_averages_absolute_contributions_across_predictions",
        "test_ablation_variant_shap_keeps_only_changed_features",
        "test_effective_contract_uses_strategy_asset_alias_and_canonical_filter",
    ),
    "AC-5009": _nodes(
        f"{_U}/service/test_v05_demo_bundle.py",
        "test_committed_bundle_is_under_budget_and_complete",
        "test_activation_mounts_isolated_copy_without_touching_formal_home",
    )
    + _nodes(
        f"{_E}/web/test_demo_bundle_flow.py",
        "test_offline_demo_bundle_wizard_flow_runs_study_wind_tunnel_ml_and_shap",
    ),
    "AC-5010": _nodes(
        f"{_U}/service/test_v05_demo_bundle.py",
        "test_activation_mounts_isolated_copy_without_touching_formal_home",
        "test_deactivation_restores_standard_mode_and_formal_home",
    )
    + _nodes(
        f"{_U}/web/test_demo_bundle_pages.py",
        "test_system_datasource_can_activate_and_exit_demo_mode",
    ),
    "AC-5011": _nodes(
        f"{_U}/test_research_cli.py",
        "test_factor_check_passes_and_returns_standard_json",
        "test_factor_check_returns_three_for_future_leak",
        "test_factor_check_missing_target_is_contract_error",
        "test_preset_cli_save_and_list_use_research_envelope",
        "test_backtest_cli_rejects_ablation_without_preset",
        "test_json_cli_survives_cp1252_pipe_with_non_bmp_roundtrip",
    )
    + _nodes(
        f"{_U}/service/test_monthly_wind_provenance.py",
        "test_cli_monthly_check_retains_declared_interval_and_price_basis",
    ),
    "AC-5012": _nodes(
        f"{_E}/test_v05_research_cli_skill.py",
        "test_skill_cli_completes_real_ablation_without_touching_paper",
    )
    + _nodes(
        f"{_U}/test_research_cli.py",
        "test_factor_init_writes_template_and_lists_it",
        "test_generated_template_passes_wind_tunnel",
        "test_factor_init_rejects_builtin_id",
        "test_json_cli_survives_cp1252_pipe_with_non_bmp_roundtrip",
    ),
    "AC-5013": _nodes(
        f"{_U}/service/test_factor_audit_badge.py",
        "test_unverified_then_pass_then_stale_on_source_change",
        "test_data_fingerprint_change_downgrades_pass_to_stale",
        "test_30m_cutoff_roundtrip_keeps_current_pass_badge",
    )
    + _nodes(
        f"{_U}/web/pages/test_factors.py",
        "test_factor_detail_renders_card_and_report_tabs",
    ),
    "AC-5014": _nodes(
        "tests/quality/test_v05_release_surface.py",
        "ReleaseSurfaceTest::test_readme_and_index_share_the_four_pillar_story",
        "ReleaseSurfaceTest::test_outdated_v05_status_phrases_are_absent",
    ),
    "AC-5015": _nodes(
        f"{_U}/data/fetchers/test_baostock_daily.py",
        "test_daily_bars_ext_normalizes_units_and_st",
        "test_calendar_and_stock_list_are_sqep_shaped",
        "test_baostock_capabilities_include_daily_but_not_market_cap",
        "test_typed_empty_frames_never_fabricate_market_cap",
    )
    + _nodes(
        f"{_U}/service/test_init_wizard.py",
        "test_baostock_source_is_token_free_and_keeps_backtest_available",
    ),
    "AC-5016": _nodes(
        f"{_U}/strategies/test_v05_pit_and_labels.py",
        "test_pit_filter_does_not_use_future_st_delisting_or_listing_state",
        "test_missing_historical_st_table_is_explicitly_warned",
        "test_panel_filter_drops_an_asset_only_on_its_st_date",
        "test_shared_st_contract_conflict_and_explicit_disabled_filter",
        "test_shared_st_contract_reports_unknown_input_without_sidecar",
        "test_listing_zero_and_boundary_contract_matches_canonical_filter",
        "test_listing_contract_applies_known_dates_when_calendar_is_missing",
        "test_panel_cache_fingerprint_tracks_all_pit_input_files",
    )
    + _nodes(
        f"{_U}/service/test_tracking_universe_contract.py",
        "test_real_status_sidecar_applies_per_profile_in_shared_refresh",
        "test_missing_history_diagnostics_survive_study_and_persisted_tracking",
        "test_unknown_status_in_persisted_sidecar_remains_missing",
        "test_tracking_source_identity_detects_auxiliary_file_revision",
    )
    + _nodes(
        f"{_U}/strategies/example/test_ml_momentum_reversal.py",
        "test_select_stocks_excludes_st_stocks",
        "test_select_stocks_excludes_up_limit_locked_stocks",
        "test_top_k_is_only_an_upper_bound_after_eligibility_filtering",
        "test_filter_universe_market_cap_trim_then_st_and_suspension",
    ),
    "AC-5017": _nodes(
        f"{_U}/strategies/test_v05_pit_and_labels.py",
        "test_raw_return_label_hand_calculated",
        "test_excess_mean_label_is_within_signal_date",
        "test_cs_rank_label_uses_average_rank_within_signal_date",
        "test_any_immature_asset_excludes_the_whole_signal_date",
        "test_model_key_changes_with_label_kind_and_pit_rules",
        "test_training_target_uses_the_selected_label_without_reranking",
        "test_labels_use_authoritative_exit_session_and_never_skip_a_gap",
        "test_authoritative_calendar_tail_keeps_middle_gap_null",
        "test_unavailable_calendar_fails_closed_without_row_shift",
    )
    + _nodes(
        f"{_U}/strategies/example/test_ml_momentum_reversal.py",
        "test_training_target_frozen_three_label_oracle",
        "test_fit_ml_model_threads_shared_seed_into_lightgbm",
        "test_strategy_seed_attribute_reaches_model_fit",
        "test_research_model_artifact_does_not_move_paper_latest",
        "test_select_stocks_lightgbm_contract_has_no_exit_metadata",
    )
    + _nodes(
        f"{_U}/strategies/test_ml_label_oracle.py",
        "test_every_mature_training_label_matches_rational_3_by_10_oracle",
        "test_training_cs_rank_uses_real_ties_and_average_ranks",
    )
    + _nodes(f"{_U}/service/test_v05_c1_identity.py", "test_model_key_encodes_effective_seed"),
    "AC-5018": _nodes(
        f"{_U}/providers/test_risk_extensions.py",
        "test_disabled_extension_never_executes_user_code",
        "test_cli_copy_example_enables_and_loads_only_example",
        "test_adapter_exposes_both_execution_factories",
    )
    + _nodes(
        f"{_U}/web/test_risk_extension_page.py",
        "test_system_page_copies_enables_and_disables_risk_extension",
    ),
    "AC-5019": _nodes(
        f"{_U}/service/test_shadow_intraday.py",
        "test_load_closed_bar_frame_ignores_forming_bucket",
        "test_latest_closed_session_slot_falls_back_to_closed_session",
        "test_first_slot_at_or_after_keeps_exact_enable_boundary",
        "test_anchor_never_invents_weekday_slots_without_authoritative_calendar",
    )
    + _nodes(f"{_U}/web/test_tracking_page.py", "test_tracking_page_renders_30m_bars_and_gaps"),
    "AC-5020": _nodes(
        f"{_U}/service/test_shadow_intraday.py",
        "test_30m_ledger_replays_full_day_t1_gap_and_restart",
        "test_shadow_actual_bar_uses_persisted_fact_not_current_broker",
        "test_real_subprocess_kill_after_committed_bar_resumes_without_duplicate",
    )
    + _nodes(
        f"{_E}/test_v05_30m_ledger.py",
        "test_two_day_ledger_matches_real_actual_and_frozen_oracle",
        "test_missing_actual_fact_is_explicit_in_tracking_output",
        "test_forming_bucket_is_provided_but_not_consumed",
        "test_sigkill_before_or_after_commit_resumes_without_duplicate_fill",
        "test_missing_actual_model_ref_does_not_fall_back_to_latest_b",
    ),
    "AC-5021": _nodes(
        "tests/quality/test_v05_release_surface.py",
        "ReleaseSurfaceTest::test_native_install_checks_and_unsigned_release_steps_are_first",
        "ReleaseSurfaceTest::test_outdated_v05_status_phrases_are_absent",
    ),
    "AC-5022": _nodes(
        "tests/quality/test_v05_edition_boundary.py",
        "CeBoundaryTest::test_official_ce_surface_does_not_bundle_pro_only_controls",
        "OpenExtensionTest::test_external_panel_columns_are_not_blacklisted",
        "OpenExtensionTest::test_custom_buffer_band_strategy_is_loaded_from_strategy_dir",
        "OpenExtensionTest::test_custom_risk_extension_loads_from_user_directory",
    ),
    "AC-5023": _nodes(
        "tests/quality/test_v05_edition_boundary.py",
        "ScopeControlTest::test_no_openapi_range_cli_was_added",
        "ScopeControlTest::test_no_alert_linkage_or_range_ui_modules_were_added",
    ),
    "AC-5024": _nodes(
        f"{_U}/audit/test_mutations.py",
        "test_every_key_mutation_is_killed_in_process",
        "test_single_case_runs_in_isolated_subprocess",
    )
    + _nodes(
        "tests/quality/test_v05_edition_boundary.py",
        "CeBoundaryTest::test_official_ce_surface_does_not_bundle_pro_only_controls",
    ),
    "AC-5025": _nodes(
        f"{_U}/service/test_init_wizard.py",
        "test_save_runtime_config_persists_workspace_directories",
        "test_save_runtime_config_defaults_blank_home_and_expands_user",
    )
    + _nodes(
        f"{_E}/web/test_directories_settings.py", "test_directories_page_persists_and_probes_paths"
    ),
    "AC-5026": _nodes(
        f"{_U}/service/test_v05_ai_agent.py",
        "test_model_error_message_never_contains_api_key",
    )
    + _nodes(
        f"{_E}/web/test_network_settings.py",
        "test_network_page_saves_lan_and_port_for_next_restart",
    ),
    "AC-5027": _nodes(
        f"{_U}/service/test_v05_ai_agent.py",
        "test_agent_repairs_bad_factor_after_first_difference",
        "test_agent_stops_after_max_repair_rounds",
    )
    + _nodes(
        f"{_E}/web/test_ai_studio_closed_loop.py",
        "test_web_studio_repairs_factor_and_runs_preset",
        "test_web_studio_real_tools_repair_against_demo_market",
    ),
    "AC-5028": _nodes(
        f"{_U}/service/test_v05_ai_studio.py",
        "test_tool_set_is_exactly_six_and_has_no_shell",
        "test_write_factor_plugin_rejects_traversal_absolute_and_builtin",
        "test_write_factor_plugin_rejects_symlink_escape",
        "test_studio_session_and_messages_persist",
    )
    + _nodes(
        f"{_U}/service/test_v05_ai_agent.py",
        "test_agent_cancel_stops_next_step",
        "test_superseded_round_cannot_overwrite_new_completed_state",
    )
    + _nodes(
        f"{_E}/web/test_ai_studio_closed_loop.py", "test_web_studio_cancel_stops_background_round"
    ),
}


_REPAIR_EVIDENCE: dict[str, tuple[str, ...]] = {
    "AC-5002": _nodes(
        f"{_U}/service/test_factor_study_tasks.py",
        "test_process_runner_enforces_memory_budget",
        "test_group_cleanup_hint_never_overrides_live_ownership",
        "test_runner_kills_nested_worker_group_after_outer_timeout",
        "test_runner_kills_leftover_child_after_normal_return",
        "test_runner_kills_term_ignoring_descendants_after_timeout",
        "test_process_runner_terminates_timeout_cancel_and_failure",
        "test_nested_timeout_leaves_no_named_semaphores_in_live_service",
        "test_isolated_result_file_handles_large_payload",
    ),
    "AC-5003": _nodes(
        f"{_U}/strategies/example/test_ml_momentum_reversal.py",
        "test_panel_cache_key_tracks_selected_factor_versions",
        "test_instance_panel_cache_rechecks_factor_identity",
        "test_explain_cache_keys_include_build_signal",
    )
    + _nodes(f"{_U}/factors/test_plugins.py", "test_verified_source_bytes_beat_stale_adjacent_pyc"),
    "AC-5013": _nodes(
        f"{_U}/service/test_factor_audit_badge.py",
        "test_bound_backtest_badge_uses_recorded_factor_version",
        "test_bound_evidence_without_run_id_never_falls_back_to_latest",
        "test_reaudit_same_source_does_not_rewrite_frozen_binding",
        "test_experiment_freezes_audit_evidence_before_model_is_known",
    ),
    "AC-5016": _nodes(
        f"{_U}/service/test_tracking_universe_contract.py",
        "test_mixed_native_group_uses_each_factors_signal_panel",
        "test_ai_study_summary_keeps_compact_universe_diagnostics",
    )
    + _nodes(
        f"{_U}/web/pages/test_ai_study_card.py", "test_study_diagnostics_reach_visible_user_card"
    ),
    "AC-5017": _nodes(
        f"{_U}/strategies/test_v05_pit_and_labels.py",
        "test_label_cache_identity_tracks_prices_and_eligibility",
    ),
    "AC-5027": _nodes(
        f"{_U}/service/test_monthly_wind_provenance.py",
        "test_ai_worker_monthly_check_preserves_raw_price_basis",
    )
    + _nodes(
        f"{_U}/service/test_ai_budget_contract.py",
        "test_refused_tool_calls_exhaust_budget_without_extra_model_turn",
        "test_http_timeout_is_not_the_total_tool_workflow_budget",
        "test_workflow_clock_budget_still_blocks_another_model_request",
    ),
    "AC-5028": _nodes(
        f"{_U}/service/test_v05_ai_agent.py",
        "test_real_slow_http_cancel_reclaims_request_thread",
        "test_cancel_before_request_holder_is_ready_is_retried",
        "test_superseded_round_cannot_persist_late_start",
        "test_cancel_without_active_round_preserves_completed_result",
        "test_cancel_commit_cannot_overwrite_new_generation",
        "test_same_generation_late_finish_cannot_override_cancelled",
        "test_old_generation_late_finish_cannot_override_new_result",
    )
    + _nodes(
        f"{_E}/web/test_ai_studio_closed_loop.py", "test_web_studio_cancel_stops_real_wind_tunnel"
    ),
}
for _ac, _evidence in _REPAIR_EVIDENCE.items():
    _V05_EVIDENCE[_ac] += _evidence
