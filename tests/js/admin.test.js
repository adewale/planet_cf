/**
 * Tests for admin dashboard JavaScript functionality
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { JSDOM } from 'jsdom';

// Helper to create a DOM environment and load the admin.js module
function createTestEnv() {
  const dom = new JSDOM(`
    <!DOCTYPE html>
    <html>
    <body>
      <div class="feed-title" data-feed-id="42">
        <span class="feed-title-text">Test Feed</span>
        <input type="text" class="feed-title-input" value="Test Feed" placeholder="Enter feed title">
        <div class="feed-title-actions">
          <button type="button" class="btn btn-success btn-sm save-title-btn">Save</button>
          <button type="button" class="btn btn-sm cancel-title-btn">Cancel</button>
        </div>
      </div>
      <div id="dlq-list"></div>
      <div id="audit-list"></div>
      <button id="reindex-btn">Reindex</button>
      <div class="tabs">
        <button class="tab active" data-tab="feeds">Feeds</button>
        <button class="tab" data-tab="dlq">DLQ</button>
      </div>
      <div id="feeds" class="tab-content active"></div>
      <div id="dlq" class="tab-content"></div>
    </body>
    </html>
  `, { url: 'http://localhost' });

  return dom;
}

// =============================================================================
// enterEditMode tests
// =============================================================================

describe('enterEditMode', () => {
  let dom;

  beforeEach(() => {
    dom = createTestEnv();
    global.document = dom.window.document;
  });

  afterEach(() => {
    dom.window.close();
  });

  it('adds editing class to title div', async () => {
    const { enterEditMode } = await import('../../assets/static/admin.js');
    const titleDiv = document.querySelector('.feed-title');

    expect(titleDiv.classList.contains('editing')).toBe(false);
    enterEditMode(titleDiv);
    expect(titleDiv.classList.contains('editing')).toBe(true);
  });

  it('focuses the input field', async () => {
    const { enterEditMode } = await import('../../assets/static/admin.js');
    const titleDiv = document.querySelector('.feed-title');
    const input = titleDiv.querySelector('.feed-title-input');

    // Mock focus
    const focusSpy = vi.spyOn(input, 'focus');
    const selectSpy = vi.spyOn(input, 'select');

    enterEditMode(titleDiv);

    expect(focusSpy).toHaveBeenCalled();
    expect(selectSpy).toHaveBeenCalled();
  });
});

// =============================================================================
// cancelEditTitle tests
// =============================================================================

describe('cancelEditTitle', () => {
  let dom;

  beforeEach(() => {
    dom = createTestEnv();
    global.document = dom.window.document;
  });

  afterEach(() => {
    dom.window.close();
  });

  it('removes editing class from title div', async () => {
    const { enterEditMode, cancelEditTitle } = await import('../../assets/static/admin.js');
    const titleDiv = document.querySelector('.feed-title');

    enterEditMode(titleDiv);
    expect(titleDiv.classList.contains('editing')).toBe(true);

    cancelEditTitle(titleDiv);
    expect(titleDiv.classList.contains('editing')).toBe(false);
  });

  it('resets input value to current text', async () => {
    const { enterEditMode, cancelEditTitle } = await import('../../assets/static/admin.js');
    const titleDiv = document.querySelector('.feed-title');
    const input = titleDiv.querySelector('.feed-title-input');

    enterEditMode(titleDiv);
    input.value = 'Modified Title';

    cancelEditTitle(titleDiv);
    expect(input.value).toBe('Test Feed');
  });

  it('clears input when text is Untitled', async () => {
    const { cancelEditTitle } = await import('../../assets/static/admin.js');
    const titleDiv = document.querySelector('.feed-title');
    const textSpan = titleDiv.querySelector('.feed-title-text');
    const input = titleDiv.querySelector('.feed-title-input');

    textSpan.textContent = 'Untitled';
    input.value = 'Some Value';

    cancelEditTitle(titleDiv);
    expect(input.value).toBe('');
  });
});

// =============================================================================
// saveFeedTitle tests
// =============================================================================

describe('saveFeedTitle', () => {
  let dom;
  let fetchMock;

  beforeEach(() => {
    dom = createTestEnv();
    global.document = dom.window.document;

    // Mock fetch
    fetchMock = vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ success: true })
    }));
    global.fetch = fetchMock;
  });

  afterEach(() => {
    dom.window.close();
    vi.restoreAllMocks();
  });

  it('removes editing class after the request resolves', async () => {
    const { enterEditMode, saveFeedTitle } = await import('../../assets/static/admin.js');
    const titleDiv = document.querySelector('.feed-title');

    enterEditMode(titleDiv);
    saveFeedTitle(titleDiv);

    // The editing class is removed inside the .then/.catch of the fetch chain,
    // i.e. asynchronously - not synchronously on the saveFeedTitle call.
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(titleDiv.classList.contains('editing')).toBe(false);
  });

  it('calls fetch with correct URL and method', async () => {
    const { saveFeedTitle } = await import('../../assets/static/admin.js');
    const titleDiv = document.querySelector('.feed-title');

    saveFeedTitle(titleDiv);

    expect(fetchMock).toHaveBeenCalledWith(
      '/admin/feeds/42',
      expect.objectContaining({
        method: 'PUT',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          'X-CSRF-Token': expect.anything()  // H15: token attached to every mutating fetch
        })
      })
    );
  });

  it('sends the trimmed title in request body', async () => {
    const { saveFeedTitle } = await import('../../assets/static/admin.js');
    const titleDiv = document.querySelector('.feed-title');
    const input = titleDiv.querySelector('.feed-title-input');

    input.value = '  New Title  ';
    saveFeedTitle(titleDiv);

    const callArgs = fetchMock.mock.calls[0];
    const body = JSON.parse(callArgs[1].body);
    expect(body.title).toBe('New Title');
  });

  it('updates text span on success', async () => {
    const { saveFeedTitle } = await import('../../assets/static/admin.js');
    const titleDiv = document.querySelector('.feed-title');
    const input = titleDiv.querySelector('.feed-title-input');
    const textSpan = titleDiv.querySelector('.feed-title-text');

    input.value = 'Updated Title';
    await saveFeedTitle(titleDiv);

    // Wait for promise chain
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(textSpan.textContent).toBe('Updated Title');
  });

  it('shows Untitled when title is empty', async () => {
    const { saveFeedTitle } = await import('../../assets/static/admin.js');
    const titleDiv = document.querySelector('.feed-title');
    const input = titleDiv.querySelector('.feed-title-input');
    const textSpan = titleDiv.querySelector('.feed-title-text');

    input.value = '';
    await saveFeedTitle(titleDiv);

    // Wait for promise chain
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(textSpan.textContent).toBe('Untitled');
  });
});

// =============================================================================
// escapeHtml tests
// =============================================================================

describe('escapeHtml', () => {
  let dom;

  beforeEach(() => {
    dom = createTestEnv();
    global.document = dom.window.document;
  });

  afterEach(() => {
    dom.window.close();
  });

  it('escapes HTML special characters', async () => {
    const { escapeHtml } = await import('../../assets/static/admin.js');

    expect(escapeHtml('<script>alert("xss")</script>')).toBe(
      '&lt;script&gt;alert("xss")&lt;/script&gt;'
    );
  });

  it('escapes ampersands', async () => {
    const { escapeHtml } = await import('../../assets/static/admin.js');

    expect(escapeHtml('foo & bar')).toBe('foo &amp; bar');
  });

  it('preserves normal text', async () => {
    const { escapeHtml } = await import('../../assets/static/admin.js');

    expect(escapeHtml('Hello World')).toBe('Hello World');
  });

  it('handles empty string', async () => {
    const { escapeHtml } = await import('../../assets/static/admin.js');

    expect(escapeHtml('')).toBe('');
  });
});

// =============================================================================
// rebuildSearchIndex tests
// =============================================================================

describe('rebuildSearchIndex', () => {
  let dom;
  let fetchMock;

  beforeEach(() => {
    dom = createTestEnv();
    global.document = dom.window.document;

    fetchMock = vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ success: true, indexed: 5, failed: 0, total: 5 })
    }));
    global.fetch = fetchMock;
  });

  afterEach(() => {
    dom.window.close();
    vi.restoreAllMocks();
  });

  it('disables button and updates text', async () => {
    const { rebuildSearchIndex } = await import('../../assets/static/admin.js');
    const btn = document.getElementById('reindex-btn');

    rebuildSearchIndex();

    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toBe('Reindexing...');
  });

  it('calls POST to /admin/reindex', async () => {
    const { rebuildSearchIndex } = await import('../../assets/static/admin.js');

    rebuildSearchIndex();

    expect(fetchMock).toHaveBeenCalledWith(
      '/admin/reindex',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-CSRF-Token': expect.anything() })
      })
    );
  });

  it('shows Done! with the indexed count on success', async () => {
    const { rebuildSearchIndex } = await import('../../assets/static/admin.js');
    const btn = document.getElementById('reindex-btn');

    await rebuildSearchIndex();
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(btn.textContent).toBe('Done! (5 indexed)');
  });

  it('shows Failed on network error', async () => {
    fetchMock.mockImplementation(() => Promise.reject(new Error('Network error')));

    const { rebuildSearchIndex } = await import('../../assets/static/admin.js');
    const btn = document.getElementById('reindex-btn');

    await rebuildSearchIndex();
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(btn.textContent).toBe('Failed');
  });
});

// =============================================================================
// loadDLQ tests
// =============================================================================

describe('loadDLQ', () => {
  let dom;
  let fetchMock;

  beforeEach(() => {
    dom = createTestEnv();
    global.document = dom.window.document;
  });

  afterEach(() => {
    dom.window.close();
    vi.restoreAllMocks();
  });

  it('shows empty state when no feeds', async () => {
    global.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ feeds: [] })
    }));

    const { loadDLQ } = await import('../../assets/static/admin.js');
    await loadDLQ();
    await new Promise(resolve => setTimeout(resolve, 0));

    const list = document.getElementById('dlq-list');
    expect(list.innerHTML).toContain('No failed feeds');
  });

  it('renders feed items with escaped content', async () => {
    global.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({
        feeds: [{
          id: 1,
          title: '<script>xss</script>',
          url: 'https://example.com',
          consecutive_failures: 5
        }]
      })
    }));

    const { loadDLQ } = await import('../../assets/static/admin.js');
    await loadDLQ();
    await new Promise(resolve => setTimeout(resolve, 0));

    const list = document.getElementById('dlq-list');
    expect(list.innerHTML).toContain('&lt;script&gt;xss&lt;/script&gt;');
    expect(list.innerHTML).not.toContain('<script>xss</script>');
  });
});

// =============================================================================
// loadAuditLog tests
// =============================================================================

describe('loadAuditLog', () => {
  let dom;

  beforeEach(() => {
    dom = createTestEnv();
    global.document = dom.window.document;
  });

  afterEach(() => {
    dom.window.close();
    vi.restoreAllMocks();
  });

  it('shows empty state when no entries', async () => {
    global.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ entries: [] })
    }));

    const { loadAuditLog } = await import('../../assets/static/admin.js');
    await loadAuditLog();
    await new Promise(resolve => setTimeout(resolve, 0));

    const list = document.getElementById('audit-list');
    expect(list.innerHTML).toContain('No audit entries');
  });

  it('renders audit entries', async () => {
    global.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({
        entries: [{
          action: 'feed_added',
          created_at: '2024-01-15T10:00:00Z',
          details: 'Added feed xyz'
        }]
      })
    }));

    const { loadAuditLog } = await import('../../assets/static/admin.js');
    await loadAuditLog();
    await new Promise(resolve => setTimeout(resolve, 0));

    const list = document.getElementById('audit-list');
    expect(list.innerHTML).toContain('feed_added');
    expect(list.innerHTML).toContain('Added feed xyz');
  });
});

// =============================================================================
// Keyboard event handling tests
// =============================================================================

describe('keyboard event handling', () => {
  let dom;
  let fetchMock;

  beforeEach(() => {
    dom = createTestEnv();
    global.document = dom.window.document;

    fetchMock = vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ success: true })
    }));
    global.fetch = fetchMock;
  });

  afterEach(() => {
    dom.window.close();
    vi.restoreAllMocks();
  });

  it('Enter key saves the title', async () => {
    const { initTitleEditing, enterEditMode } = await import('../../assets/static/admin.js');
    initTitleEditing();

    const titleDiv = document.querySelector('.feed-title');
    const input = titleDiv.querySelector('.feed-title-input');

    enterEditMode(titleDiv);
    input.value = 'New Title';

    const event = new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true });
    input.dispatchEvent(event);

    expect(fetchMock).toHaveBeenCalled();
    // The editing class is removed asynchronously inside the fetch .then/.catch.
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(titleDiv.classList.contains('editing')).toBe(false);
  });

  it('Escape key cancels editing', async () => {
    const { initTitleEditing, enterEditMode } = await import('../../assets/static/admin.js');
    initTitleEditing();

    const titleDiv = document.querySelector('.feed-title');
    const input = titleDiv.querySelector('.feed-title-input');

    enterEditMode(titleDiv);
    input.value = 'Modified';

    const event = new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true });
    input.dispatchEvent(event);

    expect(titleDiv.classList.contains('editing')).toBe(false);
    expect(input.value).toBe('Test Feed'); // Reset to original
  });
});

// =============================================================================
// Click event delegation tests
// =============================================================================

describe('click event delegation', () => {
  let dom;
  let fetchMock;

  beforeEach(() => {
    dom = createTestEnv();
    global.document = dom.window.document;

    fetchMock = vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ success: true })
    }));
    global.fetch = fetchMock;
  });

  afterEach(() => {
    dom.window.close();
    vi.restoreAllMocks();
  });

  it('clicking title text enters edit mode', async () => {
    const { initTitleEditing } = await import('../../assets/static/admin.js');
    initTitleEditing();

    const titleDiv = document.querySelector('.feed-title');
    const textSpan = titleDiv.querySelector('.feed-title-text');

    textSpan.click();

    expect(titleDiv.classList.contains('editing')).toBe(true);
  });

  it('clicking save button saves and exits edit mode', async () => {
    const { initTitleEditing, enterEditMode } = await import('../../assets/static/admin.js');
    initTitleEditing();

    const titleDiv = document.querySelector('.feed-title');
    const saveBtn = titleDiv.querySelector('.save-title-btn');

    enterEditMode(titleDiv);
    saveBtn.click();

    expect(fetchMock).toHaveBeenCalled();
    // The editing class is removed asynchronously inside the fetch .then/.catch.
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(titleDiv.classList.contains('editing')).toBe(false);
  });

  it('clicking cancel button exits edit mode without saving', async () => {
    const { initTitleEditing, enterEditMode } = await import('../../assets/static/admin.js');
    initTitleEditing();

    const titleDiv = document.querySelector('.feed-title');
    const cancelBtn = titleDiv.querySelector('.cancel-title-btn');
    const input = titleDiv.querySelector('.feed-title-input');

    enterEditMode(titleDiv);
    input.value = 'Changed';
    cancelBtn.click();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(titleDiv.classList.contains('editing')).toBe(false);
    expect(input.value).toBe('Test Feed');
  });
});
