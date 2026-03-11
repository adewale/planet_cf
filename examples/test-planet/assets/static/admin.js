// Admin dashboard functionality
// Served via Workers Static Assets from each instance's assets/static/ directory

// =============================================================================
// Feed Title Editing
// =============================================================================

function saveFeedTitle(titleDiv) {
    const feedId = titleDiv.dataset.feedId;
    const input = titleDiv.querySelector('.feed-title-input');
    const textSpan = titleDiv.querySelector('.feed-title-text');
    const newTitle = input.value.trim();

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
    })
    .catch(function(err) {
        alert('Failed to save feed title: ' + (err.message || 'Network error'));
    });

    titleDiv.classList.remove('editing');
}

function cancelEditTitle(titleDiv) {
    const textSpan = titleDiv.querySelector('.feed-title-text');
    const input = titleDiv.querySelector('.feed-title-input');
    // Reset input to current displayed value
    input.value = textSpan.textContent === 'Untitled' ? '' : textSpan.textContent;
    titleDiv.classList.remove('editing');
}

function enterEditMode(titleDiv) {
    titleDiv.classList.add('editing');
    const input = titleDiv.querySelector('.feed-title-input');
    input.focus();
    input.select();
}

// =============================================================================
// DLQ and Audit Log Loading
// =============================================================================

function loadDLQ() {
    const list = document.getElementById('dlq-list');
    return fetch('/admin/dlq')
        .then(function(r) { return r.json(); })
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
                    '<form action="/admin/feeds/' + f.id + '/retry" method="POST" style="margin-top:0.5rem">' +
                    '<button type="submit" class="btn btn-sm btn-warning">Retry</button></form>' +
                    '</div>';
            }).join('');
        })
        .catch(function(err) {
            list.innerHTML = '<p class="empty-state" style="color:var(--error)">Failed to load: ' + escapeHtml(err.message || 'Network error') + '</p>';
        });
}

function loadAuditLog() {
    const list = document.getElementById('audit-list');
    return fetch('/admin/audit')
        .then(function(r) { return r.json(); })
        .then(function(data) {
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
        })
        .catch(function(err) {
            list.innerHTML = '<p class="empty-state" style="color:var(--error)">Failed to load: ' + escapeHtml(err.message || 'Network error') + '</p>';
        });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =============================================================================
// Search Index Rebuild
// =============================================================================

function rebuildSearchIndex() {
    const btn = document.getElementById('reindex-btn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Reindexing...';
    btn.style.opacity = '0.7';

    return fetch('/admin/reindex', {
        method: 'POST'
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        btn.disabled = false;
        btn.style.opacity = '1';
        if (data.success) {
            btn.textContent = 'Done! (' + data.indexed + ' indexed)';
            setTimeout(function() { btn.textContent = originalText; }, 3000);
        } else {
            btn.textContent = 'Error: ' + (data.error || 'Unknown');
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
            const target = this.dataset.tab;
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
            const feedId = this.dataset.feedId;
            const isActive = this.checked;
            fetch('/admin/feeds/' + feedId + '/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_active: isActive })
            })
            .catch(function(err) {
                alert('Failed to toggle feed: ' + (err.message || 'Network error'));
            });
        });
    });
}

function initTitleEditing() {
    // Feed title editing - event delegation
    document.addEventListener('click', function(e) {
        // Click on title text to enter edit mode
        if (e.target.classList.contains('feed-title-text')) {
            const titleDiv = e.target.closest('.feed-title');
            enterEditMode(titleDiv);
        }
        // Save button
        if (e.target.classList.contains('save-title-btn')) {
            const titleDiv = e.target.closest('.feed-title');
            saveFeedTitle(titleDiv);
        }
        // Cancel button
        if (e.target.classList.contains('cancel-title-btn')) {
            const titleDiv = e.target.closest('.feed-title');
            cancelEditTitle(titleDiv);
        }
    });

    document.addEventListener('keydown', function(e) {
        if (e.target.classList.contains('feed-title-input')) {
            if (e.key === 'Enter') {
                e.preventDefault();
                const titleDiv = e.target.closest('.feed-title');
                saveFeedTitle(titleDiv);
            } else if (e.key === 'Escape') {
                const titleDiv = e.target.closest('.feed-title');
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
