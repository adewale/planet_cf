// Admin dashboard functionality
// Served via Workers Static Assets from each instance's assets/static/ directory

// =============================================================================
// Feed Title Editing
// =============================================================================

function saveFeedTitle(titleDiv) {
    var feedId = titleDiv.dataset.feedId;
    var input = titleDiv.querySelector('.feed-title-input');
    var textSpan = titleDiv.querySelector('.feed-title-text');
    var newTitle = input.value.trim();

    fetch('/admin/feeds/' + feedId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
        body: JSON.stringify({ title: newTitle })
    })
    .then(function(r) {
        if (!r.ok) throw new Error('Server error: ' + r.status);
        return r.json();
    })
    .then(function(data) {
        if (data.success) {
            textSpan.textContent = newTitle || 'Untitled';
        }
        titleDiv.classList.remove('editing');
    })
    .catch(function(err) {
        titleDiv.classList.remove('editing');
        alert('Failed to save feed title: ' + (err.message || 'Network error'));
    });
}

function cancelEditTitle(titleDiv) {
    var textSpan = titleDiv.querySelector('.feed-title-text');
    var input = titleDiv.querySelector('.feed-title-input');
    // Reset input to current displayed value
    input.value = textSpan.textContent === 'Untitled' ? '' : textSpan.textContent;
    titleDiv.classList.remove('editing');
}

function enterEditMode(titleDiv) {
    titleDiv.classList.add('editing');
    var input = titleDiv.querySelector('.feed-title-input');
    input.focus();
    input.select();
}

// =============================================================================
// Timestamp parsing
// =============================================================================

// SQLite stores audit timestamps as "YYYY-MM-DD HH:MM:SS" in UTC, but
// `new Date("YYYY-MM-DD HH:MM:SS")` is implementation-defined and most engines
// parse it as *local* time (or Invalid Date). Normalize to ISO 8601 with an
// explicit UTC designator before parsing. ISO strings that already carry a
// timezone (e.g. "...Z" or "...+00:00") are passed through unchanged.
function parseTimestamp(value) {
    if (!value) return new Date(NaN);
    var s = String(value);
    // "YYYY-MM-DD HH:MM:SS" -> "YYYY-MM-DDTHH:MM:SS"
    if (s.indexOf('T') === -1 && s.indexOf(' ') !== -1) {
        s = s.replace(' ', 'T');
    }
    // Append Z only when no timezone designator is present.
    if (!/[Zz]$|[+-]\d{2}:?\d{2}$/.test(s)) {
        s += 'Z';
    }
    return new Date(s);
}

// =============================================================================
// DLQ and Audit Log Loading
// =============================================================================

function loadDLQ() {
    var list = document.getElementById('dlq-list');
    return fetch('/admin/dlq')
        .then(function(r) {
            if (!r.ok) throw new Error('Server error: ' + r.status);
            return r.json();
        })
        .then(function(data) {
            if (!data.feeds || data.feeds.length === 0) {
                list.innerHTML = '<p class="empty-state">No failed feeds</p>';
                return;
            }
            list.innerHTML = data.feeds.map(function(f) {
                return '<div class="dlq-item">' +
                    '<strong>' + escapeHtml(f.title || 'Untitled') + '</strong><br>' +
                    '<small>' + escapeHtml(f.url) + '</small><br>' +
                    '<small>Failures: ' + f.consecutive_failures + '</small>' +
                    '<form action="/admin/dlq/' + f.id + '/retry" method="POST" class="dlq-retry-form">' +
                    '<input type="hidden" name="csrf_token" value="' + escapeHtml(csrfToken()) + '">' +
                    '<button type="submit" class="btn btn-sm btn-warning">Retry</button></form>' +
                    '</div>';
            }).join('');
        })
        .catch(function(err) {
            list.innerHTML = '<p class="empty-state empty-state-error">Failed to load: ' + escapeHtml(err.message || 'Network error') + '</p>';
        });
}

function loadAuditLog() {
    var list = document.getElementById('audit-list');
    return fetch('/admin/audit')
        .then(function(r) {
            if (!r.ok) throw new Error('Server error: ' + r.status);
            return r.json();
        })
        .then(function(data) {
            if (!data.entries || data.entries.length === 0) {
                list.innerHTML = '<p class="empty-state">No audit entries</p>';
                return;
            }
            list.innerHTML = data.entries.map(function(e) {
                return '<div class="audit-item">' +
                    '<span class="audit-action">' + escapeHtml(e.action) + '</span> ' +
                    '<span class="audit-time">' + parseTimestamp(e.created_at).toLocaleString() + '</span>' +
                    '<div class="audit-details">' + escapeHtml(e.details || '') + '</div>' +
                    '</div>';
            }).join('');
        })
        .catch(function(err) {
            list.innerHTML = '<p class="empty-state empty-state-error">Failed to load: ' + escapeHtml(err.message || 'Network error') + '</p>';
        });
}

function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// H15: CSRF token, rendered into a <meta name="csrf-token"> tag on admin pages.
// Sent as the X-CSRF-Token header on every state-changing fetch, and injected
// into dynamically-built form posts (the DLQ retry form).
function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

// =============================================================================
// Search Index Rebuild
// =============================================================================

function rebuildSearchIndex() {
    var btn = document.getElementById('reindex-btn');
    var originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Reindexing...';
    btn.style.opacity = '0.7';

    return fetch('/admin/reindex', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken() }
    })
    .then(function(r) {
        // Surface the server's message (e.g. the 429 cooldown text) instead of
        // a generic failure. Parse the JSON body regardless of status, then
        // decide what to show.
        return r.json().then(function(data) {
            return { ok: r.ok, status: r.status, data: data };
        }).catch(function() {
            return { ok: r.ok, status: r.status, data: {} };
        });
    })
    .then(function(result) {
        btn.disabled = false;
        btn.style.opacity = '1';
        var data = result.data || {};
        if (result.ok && data.success) {
            btn.textContent = 'Done! (' + data.indexed + ' indexed)';
            setTimeout(function() { btn.textContent = originalText; }, 3000);
        } else {
            // Prefer the server-supplied error (covers the 429 cooldown message).
            var msg = data.error || ('Error: ' + result.status);
            btn.textContent = msg;
            setTimeout(function() { btn.textContent = originalText; }, 3000);
        }
    })
    .catch(function() {
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.textContent = 'Failed';
        setTimeout(function() { btn.textContent = originalText; }, 3000);
    });
}

// =============================================================================
// Event Handlers (attached on DOMContentLoaded)
// =============================================================================

function initAdminDashboard() {
    // Tab switching
    document.querySelectorAll('.tab').forEach(function(tab) {
        tab.addEventListener('click', function() {
            var target = this.dataset.tab;
            document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
            document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
            this.classList.add('active');
            document.getElementById(target).classList.add('active');
            if (target === 'dlq') loadDLQ();
            if (target === 'audit') loadAuditLog();
        });
    });

    // Feed toggles (dashboard checkbox switches)
    document.querySelectorAll('.feed-toggle').forEach(function(toggle) {
        toggle.addEventListener('change', function() {
            var checkbox = this;
            var feedId = checkbox.dataset.feedId;
            var isActive = checkbox.checked;
            fetch('/admin/feeds/' + feedId + '/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
                body: JSON.stringify({ is_active: isActive })
            })
            .then(function(r) {
                if (!r.ok) throw new Error('Server error: ' + r.status);
            })
            .catch(function(err) {
                // Revert the visual state so the checkbox reflects reality.
                checkbox.checked = !isActive;
                alert('Failed to toggle feed: ' + (err.message || 'Network error'));
            });
        });
    });

    // Reindex button (H4: inline onclick removed; bind here so CSP 'self' allows it)
    var reindexBtn = document.getElementById('reindex-btn');
    if (reindexBtn) {
        reindexBtn.addEventListener('click', rebuildSearchIndex);
    }

    initConfirmHandlers();
    initFeedToggleButtons();
}

// H4: delegated confirmation handler. Elements carrying `js-confirm` and a
// `data-confirm="..."` message replace the old inline
// `onclick="return confirm(...)"`. For a submit button this must gate the
// form's submission, so we listen on submit (the canonical cancellable event)
// and also on click as a fallback for non-submit activations.
function initConfirmHandlers() {
    document.addEventListener('submit', function(e) {
        var form = e.target;
        // A js-confirm submit button (or the form itself) inside this form.
        var trigger = form.querySelector('.js-confirm[data-confirm]');
        if (form.classList && form.classList.contains('js-confirm') && form.dataset.confirm) {
            trigger = form;
        }
        if (trigger && !confirm(trigger.dataset.confirm)) {
            e.preventDefault();
        }
    });

    // Fallback for js-confirm elements that are not inside a form (e.g. links
    // or buttons that act directly). Submit-button clicks are handled by the
    // submit listener above; intercepting them here too would double-prompt.
    document.addEventListener('click', function(e) {
        var el = e.target.closest ? e.target.closest('.js-confirm[data-confirm]') : null;
        if (!el) return;
        // If this element will trigger a form submit, let the submit handler
        // own the confirmation to avoid prompting twice.
        if (el.form || (el.type === 'submit') || el.closest('form')) return;
        if (!confirm(el.dataset.confirm)) {
            e.preventDefault();
        }
    });
}

// H6: health-page Activate/Deactivate buttons. Replaces the broken
// `_method=PUT` form by POSTing to the existing /toggle JSON endpoint and
// refreshing the page to reflect the new state.
function initFeedToggleButtons() {
    document.querySelectorAll('.js-feed-toggle').forEach(function(el) {
        el.addEventListener('click', function(e) {
            e.preventDefault();
            var feedId = el.dataset.feedId;
            // data-active is the feed's CURRENT state; we flip it.
            var currentlyActive = el.dataset.active === '1' || el.dataset.active === 'true';
            var nextActive = !currentlyActive;
            el.disabled = true;
            fetch('/admin/feeds/' + feedId + '/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
                body: JSON.stringify({ is_active: nextActive })
            })
            .then(function(r) {
                if (!r.ok) throw new Error('Server error: ' + r.status);
                // Refresh so the row/page reflects the new state.
                window.location.reload();
            })
            .catch(function(err) {
                el.disabled = false;
                alert('Failed to update feed: ' + (err.message || 'Network error'));
            });
        });
    });
}

function initTitleEditing() {
    // Feed title editing - event delegation
    document.addEventListener('click', function(e) {
        // Click on title text to enter edit mode
        if (e.target.classList.contains('feed-title-text')) {
            var titleDiv = e.target.closest('.feed-title');
            enterEditMode(titleDiv);
        }
        // Save button
        if (e.target.classList.contains('save-title-btn')) {
            var titleDiv = e.target.closest('.feed-title');
            saveFeedTitle(titleDiv);
        }
        // Cancel button
        if (e.target.classList.contains('cancel-title-btn')) {
            var titleDiv = e.target.closest('.feed-title');
            cancelEditTitle(titleDiv);
        }
    });

    document.addEventListener('keydown', function(e) {
        if (e.target.classList.contains('feed-title-input')) {
            if (e.key === 'Enter') {
                e.preventDefault();
                var titleDiv = e.target.closest('.feed-title');
                saveFeedTitle(titleDiv);
            } else if (e.key === 'Escape') {
                var titleDiv = e.target.closest('.feed-title');
                cancelEditTitle(titleDiv);
            }
        }
    });
}

// =============================================================================
// Initialize on DOM ready
// =============================================================================

if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function() {
        initAdminDashboard();
        initTitleEditing();
    });
}

// =============================================================================
// Exports for testing
// =============================================================================

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        saveFeedTitle,
        cancelEditTitle,
        enterEditMode,
        parseTimestamp,
        loadDLQ,
        loadAuditLog,
        escapeHtml,
        rebuildSearchIndex,
        initAdminDashboard,
        initConfirmHandlers,
        initFeedToggleButtons,
        initTitleEditing
    };
}
