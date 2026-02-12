# vulture_whitelist.py
# Whitelist for vulture dead code detection.
# Items listed here are intentionally "unused" in src/ but used elsewhere
# (tests, runtime entry points, JavaScript boundary layer, etc.).
#
# Format: reference the symbol so vulture sees it as "used".
# Run: uvx vulture src/ vulture_whitelist.py

# =============================================================================
# Cloudflare Workers entry points (called by runtime, not by Python code)
# =============================================================================
from main import Default

Default.fetch  # HTTP request handler - called by Workers runtime
Default.scheduled  # Cron trigger - called by Workers runtime
Default.queue  # Queue consumer - called by Workers runtime

# =============================================================================
# Test-only types in models.py (used in tests, not imported by src/)
# =============================================================================
from models import (
    AdminId,
    AdminRow,
    AuditAction,
    ContentType,
    EntryId,
    EntryRow,
    Err,
    FeedJob,
    FeedRow,
    FeedStatus,
    FetchError,
    NoOpSanitizer,
    Ok,
    ParsedEntry,
    Result,
    Session,
)

FeedJob  # unused class (used in tests)
FeedJob.to_dict  # unused method (used in tests)
FeedJob.from_dict  # unused method (used in tests)
Session  # unused class (used in tests)
Session.is_expired  # unused method (used in tests)
Session.to_json  # unused method (used in tests)
Session.from_json  # unused method (used in tests)
ParsedEntry  # unused class (used in tests)
ParsedEntry.from_feedparser  # unused method (used in tests)
FeedRow  # unused class (used in tests for type documentation)
EntryRow  # unused class (used in tests for type documentation)
AdminRow  # unused class (used in tests for type documentation)
Ok  # unused class (used in tests)
Err  # unused class (used in tests)
Result  # unused type alias (used in tests)
FetchError  # unused class (used in tests)
FetchError.is_permanent  # unused method (used in tests)
FetchError.is_transient  # unused method (used in tests)
FetchError.PARSE_ERROR  # unused variable
FetchError.EMPTY_FEED  # unused variable
NoOpSanitizer  # unused class (used in tests)
EntryId  # unused variable (semantic type alias, used for type safety)
AdminId  # unused variable (semantic type alias, used for type safety)
AuditAction  # unused variable (type alias for audit actions)
FeedStatus  # unused variable (type alias for feed status)
ContentType  # unused variable (type alias for content types)

# TypedDict fields are accessed dynamically, not through attribute access
FeedRow.consecutive_failures  # unused variable
FeedRow.last_success_at  # unused variable
FeedRow.last_error_at  # unused variable
FeedRow.last_error_message  # unused variable
FeedRow.created_at  # unused variable
FeedRow.updated_at  # unused variable
FeedRow.last_fetch_at  # unused variable
FeedRow.fetch_error  # unused variable
FeedRow.fetch_error_count  # unused variable
EntryRow.created_at  # unused variable
EntryRow.first_seen  # unused variable
EntryRow.feed_site_url  # unused variable
AdminRow.display_name  # unused variable
AdminRow.last_login_at  # unused variable
AdminRow.created_at  # unused variable

# =============================================================================
# route_dispatcher.py - used in tests
# =============================================================================
from route_dispatcher import RouteMatch, create_default_routes

create_default_routes  # unused function (used in tests)
RouteMatch.path_params  # unused variable (used in pattern matching)

# RouteDispatcher methods used in tests
from route_dispatcher import RouteDispatcher

RouteDispatcher.add_route  # unused method (used in tests)
RouteDispatcher.get_route_name  # unused method (used in tests)

# =============================================================================
# utils.py - used in tests
# =============================================================================
from utils import format_datetime, xml_escape

xml_escape  # unused function (used in tests)
format_datetime  # unused function (referenced in docs/spec)

# =============================================================================
# wrappers.py - underscore functions imported by main.py
# =============================================================================
from wrappers import (
    SafeFormData,
    SafeHeaders,
    _extract_form_value,
    _is_js_undefined,
    _safe_str,
    _to_d1_value,
    _to_js_value,
    _to_py_list,
    _to_py_safe,
)

_to_js_value  # unused function (imported by main.py)
_is_js_undefined  # unused function (imported by main.py)
_safe_str  # unused function (imported by main.py)
_to_py_safe  # unused function (imported by main.py)
_extract_form_value  # unused function (imported by wrappers.py SafeFormData)
_to_py_list  # unused function (imported by main.py)
_to_d1_value  # unused function (used by SafeD1Statement.bind)

# SafeHeaders/SafeFormData methods used at runtime
SafeHeaders.accept  # unused property (available for runtime use)
SafeFormData.get_str  # unused method (used in tests)
SafeFormData.get_int  # unused method (used in tests)

# =============================================================================
# auth.py - used for cookie management
# =============================================================================
from auth import create_session_cookie

create_session_cookie  # unused function (available for session management)

# =============================================================================
# config.py - accessor functions used in tests
# =============================================================================
from config import (
    get_embedding_max_chars,
    get_feed_auto_deactivate_threshold,
    get_feed_failure_threshold,
    get_feed_timeout,
    get_http_timeout,
    get_max_entries_per_feed,
    get_planet_config,
    get_retention_days,
    get_search_score_threshold,
    get_search_top_k,
)

get_planet_config  # unused function (used in tests)
get_retention_days  # unused function (used in tests)
get_max_entries_per_feed  # unused function (used in tests)
get_embedding_max_chars  # unused function (used in tests)
get_search_score_threshold  # unused function (used in tests)
get_search_top_k  # unused function (used in tests)
get_feed_auto_deactivate_threshold  # unused function (used in tests)
get_feed_failure_threshold  # unused function (used in tests)
get_feed_timeout  # unused function (used in tests)
get_http_timeout  # unused function (used in tests)

# =============================================================================
# admin.py - helper functions used by main.py
# =============================================================================
from admin import (
    format_feed_validation_result,
    log_admin_action,
    parse_opml,
    validate_opml_feeds,
)

parse_opml  # unused function (used by main.py _import_opml)
validate_opml_feeds  # unused function (used by main.py _import_opml)
format_feed_validation_result  # unused function (used by main.py)
log_admin_action  # unused function (used by main.py)

# =============================================================================
# content_processor.py - used in tests
# =============================================================================
from content_processor import process_entry

process_entry  # unused function (used in tests)

# =============================================================================
# search_query.py - used in tests
# =============================================================================
from search_query import SearchQueryBuilder

SearchQueryBuilder.from_raw_query  # unused method (used in tests)

# =============================================================================
# templates.py - Jinja2 loader method (called by Jinja2 framework)
# =============================================================================
from templates import (
    THEME_LOGOS,
    EmbeddedLoader,
)

EmbeddedLoader.get_source  # unused method (called by Jinja2 Environment)
_.environment  # Jinja2 loader interface parameter

# Theme/template constants (generated by build_templates.py, used externally)
THEME_LOGOS  # unused variable (per-theme logo paths, available for use)

# =============================================================================
# observability.py - dataclass fields set at runtime via attribute assignment
# =============================================================================
# These are wide event fields populated dynamically during request/feed processing.
# Vulture sees them as unused because they're dataclass defaults, but they're
# set via attribute assignment (e.g., event.outcome = "success") at runtime.
from observability import (
    AdminActionEvent,
    FeedFetchEvent,
    RequestEvent,
    SchedulerEvent,
    Timer,
)

# RequestEvent fields
RequestEvent.response_size_bytes
RequestEvent.search_query
RequestEvent.search_query_length
RequestEvent.search_words_truncated
RequestEvent.search_embedding_ms
RequestEvent.search_vectorize_ms
RequestEvent.search_d1_ms
RequestEvent.search_results_total
RequestEvent.search_semantic_matches
RequestEvent.search_keyword_matches
RequestEvent.search_exact_title_matches
RequestEvent.search_title_in_query_matches
RequestEvent.search_query_in_title_matches
RequestEvent.search_semantic_error
RequestEvent.search_keyword_error
RequestEvent.generation_d1_ms
RequestEvent.generation_render_ms
RequestEvent.generation_entries_total
RequestEvent.generation_feeds_healthy
RequestEvent.generation_trigger
RequestEvent.generation_used_fallback
RequestEvent.oauth_stage
RequestEvent.oauth_provider
RequestEvent.oauth_success
RequestEvent.oauth_username
RequestEvent.outcome

# FeedFetchEvent fields
FeedFetchEvent.queue_message_id
FeedFetchEvent.feed_url_original
FeedFetchEvent.feed_consecutive_failures
FeedFetchEvent.feed_auto_deactivated
FeedFetchEvent.http_latency_ms
FeedFetchEvent.http_status
FeedFetchEvent.http_cached
FeedFetchEvent.http_redirected
FeedFetchEvent.response_size_bytes
FeedFetchEvent.etag_present
FeedFetchEvent.last_modified_present
FeedFetchEvent.parse_errors
FeedFetchEvent.upsert_failures
FeedFetchEvent.content_fetched_count
FeedFetchEvent.indexing_attempted
FeedFetchEvent.indexing_succeeded
FeedFetchEvent.indexing_failed
FeedFetchEvent.indexing_total_ms
FeedFetchEvent.indexing_embedding_ms
FeedFetchEvent.indexing_upsert_ms
FeedFetchEvent.indexing_text_truncated
FeedFetchEvent.outcome
FeedFetchEvent.error_retriable
FeedFetchEvent.deployment_environment
FeedFetchEvent.error_category
FeedFetchEvent.queue_attempt

# SchedulerEvent fields
SchedulerEvent.scheduler_d1_ms
SchedulerEvent.scheduler_queue_ms
SchedulerEvent.feeds_queried
SchedulerEvent.feeds_active
SchedulerEvent.feeds_enqueued
SchedulerEvent.feeds_recovery_attempted
SchedulerEvent.feeds_disabled
SchedulerEvent.feeds_newly_disabled
SchedulerEvent.error_clusters
SchedulerEvent.error_cluster_top
SchedulerEvent.dlq_depth
SchedulerEvent.retention_d1_ms
SchedulerEvent.retention_vectorize_ms
SchedulerEvent.retention_entries_scanned
SchedulerEvent.retention_entries_deleted
SchedulerEvent.retention_vectors_deleted
SchedulerEvent.retention_errors
SchedulerEvent.retention_max_per_feed
SchedulerEvent.outcome
SchedulerEvent.deployment_environment

# AdminActionEvent fields
AdminActionEvent.import_file_size
AdminActionEvent.import_feeds_parsed
AdminActionEvent.import_feeds_added
AdminActionEvent.import_feeds_skipped
AdminActionEvent.import_errors
AdminActionEvent.reindex_entries_total
AdminActionEvent.reindex_entries_indexed
AdminActionEvent.reindex_entries_failed
AdminActionEvent.reindex_total_ms
AdminActionEvent.dlq_feed_id
AdminActionEvent.dlq_original_error
AdminActionEvent.dlq_action
AdminActionEvent.outcome
AdminActionEvent.deployment_environment

# Timer.__exit__ parameters (required by context manager protocol)
Timer.__exit__  # exc_type, exc_val, exc_tb are required by __exit__ signature

# =============================================================================
# main.py - runtime attribute assignments and aliases
# =============================================================================
from main import Default as _Default

_Default._generate_html  # triggered_by parameter used at runtime
_Default._serve_health  # public /health endpoint

from main import _classify_error

_classify_error  # unused function (used in queue handler)

# PlanetCF alias in main.py (used by tests that import PlanetCF)
from main import PlanetCF  # noqa: F811

PlanetCF  # unused variable (test alias for Default class)

# Variables used for observability logging (assigned but not read in same scope)
_.keyword_content_count  # unused variable (used for observability metrics)
_.semantic_only_count  # unused variable (used for observability metrics)

# =============================================================================
# admin_context.py - internal state used by context manager
# =============================================================================
from admin_context import AdminActionContext

AdminActionContext._success  # unused attribute (internal state for context manager)

# =============================================================================
# Timer.__exit__ parameters (required by Python context manager protocol)
# =============================================================================
_.exc_type  # unused variable (required by __exit__ signature)
_.exc_val  # unused variable (required by __exit__ signature)
_.exc_tb  # unused variable (required by __exit__ signature)

# main.py parameter used for admin-triggered generation
_.triggered_by  # unused variable (parameter for admin manual refresh tracking)
