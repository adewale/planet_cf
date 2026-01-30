// Admin dashboard functionality
// This file is the source of truth - ADMIN_JS in templates.py should match

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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            textSpan.textContent = newTitle || 'Untitled';
        }
    });

    titleDiv.classList.remove('editing');
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
// DLQ and Audit Log Loading
// =============================================================================

function loadDLQ() {
    fetch('/admin/dlq')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var list = document.getElementById('dlq-list');
            if (!data.feeds || data.feeds.length === 0) {
                list.innerHTML = '<p class="empty-state">No failed feeds</p>';
                return;
            }
            list.innerHTML = data.feeds.map(function(f) {
                return '<div class="dlq-item">' +
                    '<strong>' + escapeHtml(f.title || 'Untitled') + '</strong><br>' +
                    '<small>' + escapeHtml(f.url) + '</small><br>' +
                    '<small>Failures: ' + f.consecutive_failures + '</small>' +
                    '<form action="/admin/feeds/' + f.id + '/retry" method="POST" style="margin-top:0.5rem">' +
                    '<button type="submit" class="btn btn-sm btn-warning">Retry</button></form>' +
                    '</div>';
            }).join('');
        });
}

function loadAuditLog() {
    fetch('/admin/audit')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var list = document.getElementById('audit-list');
            if (!data.entries || data.entries.length === 0) {
                list.innerHTML = '<p class="empty-state">No audit entries</p>';
                return;
            }
            list.innerHTML = data.entries.map(function(e) {
                return '<div class="audit-item">' +
                    '<span class="audit-action">' + escapeHtml(e.action) + '</span> ' +
                    '<span class="audit-time">' + new Date(e.created_at).toLocaleString() + '</span>' +
                    '<div class="audit-details">' + escapeHtml(e.details || '') + '</div>' +
                    '</div>';
            }).join('');
        });
}

function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =============================================================================
// Search Index Rebuild
// =============================================================================

function rebuildSearchIndex() {
    var btn = document.getElementById('reindex-btn');
    btn.disabled = true;
    btn.textContent = 'Reindexing...';

    fetch('/admin/reindex', { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            btn.textContent = data.success ? 'Done!' : 'Failed';
            setTimeout(function() {
                btn.disabled = false;
                btn.textContent = 'Reindex';
            }, 2000);
        })
        .catch(function() {
            btn.textContent = 'Failed';
            setTimeout(function() {
                btn.disabled = false;
                btn.textContent = 'Reindex';
            }, 2000);
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

    // Feed toggles
    document.querySelectorAll('.feed-toggle').forEach(function(toggle) {
        toggle.addEventListener('change', function() {
            var feedId = this.dataset.feedId;
            var isActive = this.checked;
            fetch('/admin/feeds/' + feedId + '/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_active: isActive })
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
        loadDLQ,
        loadAuditLog,
        escapeHtml,
        rebuildSearchIndex,
        initAdminDashboard,
        initTitleEditing
    };
}
