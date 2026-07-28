async function openMemoryEditor() {
    if (!window.orangeBridge?.isAvailable()) return;
    openModal('memory-editor-modal');
    const list = document.getElementById('memory-editor-list');
    if (list) {
        list.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">LOADING_MEMORY...</div>';
    }
    try {
        const payload = await window.orangeBridge.json('api_get_memory_items', 300);
        if (payload.status !== 'success') {
            throw new Error(payload.message || 'Memory load failed');
        }
        renderMemoryEditor(payload.items || []);
    } catch (error) {
        if (list) {
            list.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(error.toString())}</div>`;
        }
    }
}

function renderMemoryEditor(items) {
    const list = document.getElementById('memory-editor-list');
    if (!list) return;
    if (!items.length) {
        list.innerHTML = '<div class="p-3 text-on-surface-variant font-label-mono text-[11px]">NO_MEMORY_ITEMS</div>';
        return;
    }
    list.innerHTML = '';
    items.forEach(item => {
        const isPinned = item.is_pinned === 1 || item.is_pinned === true;
        const isExcluded = item.exclude_from_rag === 1 || item.exclude_from_rag === true;
        const row = document.createElement('div');
        row.className = "border border-outline p-3 bg-black/30 flex flex-col gap-2";
        row.innerHTML = `
            <div class="flex items-center justify-between gap-3 border-b border-outline pb-2">
                <div class="min-w-0">
                    <div class="font-label-mono text-[10px] text-primary truncate">${escapeHTML(item.title || 'Untitled')} / ${escapeHTML(item.role || '')}</div>
                    <div class="font-label-mono text-[10px] text-on-surface-variant">${escapeHTML(item.timestamp || '')}</div>
                </div>
                <div class="flex gap-2 shrink-0">
                    <button onclick="toggleMemoryFlag(${item.id}, 'pin', ${isPinned ? 'false' : 'true'})" class="${isPinned ? 'bg-primary text-on-primary' : 'border border-outline text-on-surface'} px-2 py-1 font-label-mono text-[10px]">PIN</button>
                    <button onclick="toggleMemoryFlag(${item.id}, 'rag', ${isExcluded ? 'false' : 'true'})" class="${isExcluded ? 'bg-error text-on-error' : 'border border-outline text-on-surface'} px-2 py-1 font-label-mono text-[10px]">NO_RAG</button>
                    <button onclick="deleteMemoryItem(${item.id})" class="border border-error text-error px-2 py-1 font-label-mono text-[10px]">DELETE</button>
                </div>
            </div>
            <div class="font-body-sm text-body-sm text-on-surface whitespace-pre-wrap break-words">${escapeHTML((item.content || '').slice(0, 1200))}</div>
        `;
        list.appendChild(row);
    });
}

async function toggleMemoryFlag(messageId, flag, value) {
    if (!window.orangeBridge?.isAvailable()) return;
    const isPinned = flag === 'pin' ? value : null;
    const excludeFromRag = flag === 'rag' ? value : null;
    try {
        const payload = await window.orangeBridge.json(
            'api_update_memory_item',
            messageId,
            isPinned,
            excludeFromRag,
        );
        if (payload.status !== 'success') {
            throw new Error(payload.message || 'Update failed');
        }
        await openMemoryEditor();
    } catch (error) {
        appendMessage('System', `Memory update failed: ${error.toString()}`, 'sys');
    }
}

async function deleteMemoryItem(messageId) {
    if (!window.orangeBridge?.isAvailable() || !confirm('Delete this memory item?')) return;
    try {
        const payload = await window.orangeBridge.json('api_delete_memory_item', messageId);
        if (payload.status !== 'success') {
            throw new Error(payload.message || 'Delete failed');
        }
        await openMemoryEditor();
    } catch (error) {
        appendMessage('System', `Memory delete failed: ${error.toString()}`, 'sys');
    }
}

async function openSmartInbox() {
    if (!window.orangeBridge?.isAvailable()) return;
    openModal('smart-inbox-modal');
    const list = document.getElementById('smart-inbox-list');
    if (list) {
        list.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">SCANNING_INBOX...</div>';
    }
    try {
        const payload = await window.orangeBridge.json('api_get_inbox_proposals');
        if (payload.status !== 'success') {
            throw new Error(payload.message || 'Inbox scan failed');
        }
        smartInboxProposals = payload.items || [];
        renderSmartInbox();
    } catch (error) {
        if (list) {
            list.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(error.toString())}</div>`;
        }
    }
}

function addSmartInboxProposal(proposal) {
    const key = proposal.file_path || proposal.relative_path || proposal.filename;
    smartInboxProposals = smartInboxProposals.filter(item =>
        (item.file_path || item.relative_path || item.filename) !== key
    );
    smartInboxProposals.unshift(proposal);
    appendMessage(
        'Smart Inbox',
        `Proposal: ${(proposal.category || 'note').toUpperCase()} / ${proposal.filename || key}`,
        'sys',
    );
    if (!document.getElementById('smart-inbox-modal')?.classList.contains('hidden')) {
        renderSmartInbox();
    }
}

function renderSmartInbox() {
    const list = document.getElementById('smart-inbox-list');
    if (!list) return;
    if (!smartInboxProposals.length) {
        list.innerHTML = '<div class="p-3 text-on-surface-variant font-label-mono text-[11px]">NO_INBOX_PROPOSALS</div>';
        return;
    }
    list.innerHTML = '';
    smartInboxProposals.forEach((item, index) => {
        const row = document.createElement('div');
        row.className = "border border-outline p-3 bg-black/30 flex flex-col gap-2";
        if (item.status === 'error') {
            row.innerHTML = `<div class="text-error font-label-mono text-[11px]">${escapeHTML(item.filename || '')}: ${escapeHTML(item.message || 'Error')}</div>`;
        } else {
            const confidence = Number(item.confidence);
            const confidenceLabel = Number.isFinite(confidence)
                ? `${Math.round(confidence * 100)}%`
                : '—';
            row.innerHTML = `
                <div class="flex items-center justify-between gap-3">
                    <div class="min-w-0">
                        <div class="font-label-mono text-[10px] text-primary truncate">${escapeHTML(item.filename || '')}</div>
                        <div class="font-label-mono text-[10px] text-on-surface-variant break-words">${escapeHTML(item.relative_path || item.file_path || '')}</div>
                    </div>
                    <span class="border border-primary text-primary px-2 py-1 font-label-mono text-[10px] shrink-0">${escapeHTML((item.category || 'idea').toUpperCase())} / ${escapeHTML(confidenceLabel)}</span>
                </div>
                <div class="font-body-sm text-body-sm text-on-surface">${escapeHTML(item.summary || '')}</div>
                <div class="flex justify-end">
                    <button onclick="applyInboxProposalByIndex(${index})" class="border border-primary text-primary hover:bg-primary hover:text-on-primary px-3 py-1 font-label-mono text-[10px]">APPLY_AFTER_CONFIRM</button>
                </div>
            `;
        }
        list.appendChild(row);
    });
}

function applyInboxProposalByIndex(index) {
    const item = smartInboxProposals[index];
    if (!item) return;
    applyInboxProposal(
        item.file_path || '',
        item.category || '',
        item.proposal_id || '',
    );
}

async function applyInboxProposal(filePath, category, proposalId = '') {
    if (!window.orangeBridge?.isAvailable() || !confirm('Apply this Smart Inbox proposal?')) return;
    try {
        const payload = await window.orangeBridge.json(
            'api_apply_inbox_proposal',
            filePath,
            category,
            proposalId,
        );
        if (payload.status !== 'success') {
            throw new Error(payload.message || 'Apply failed');
        }
        appendMessage('Smart Inbox', payload.message, 'sys');
        await openSmartInbox();
    } catch (error) {
        appendMessage('Smart Inbox', `Apply failed: ${error.toString()}`, 'sys');
    }
}

async function openMorningDashboard() {
    if (!window.orangeBridge?.isAvailable()) return;
    openModal('morning-dashboard-modal');
    const content = document.getElementById('morning-dashboard-content');
    if (content) {
        content.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">BUILDING_DASHBOARD...</div>';
    }
    try {
        const payload = await window.orangeBridge.json('api_get_morning_dashboard');
        if (payload.status !== 'success') {
            throw new Error(payload.message || 'Dashboard failed');
        }
        renderMorningDashboard(payload.dashboard || payload.data || {});
    } catch (error) {
        if (content) {
            content.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(error.toString())}</div>`;
        }
    }
}

function renderMorningDashboard(dashboard) {
    const content = document.getElementById('morning-dashboard-content');
    if (!content) return;
    const section = (title, items, formatter) => `
        <section class="border border-outline p-3 bg-black/30 min-h-[120px]">
            <div class="font-label-caps text-label-caps text-primary border-b border-outline pb-2 mb-2">${escapeHTML(title)}</div>
            <div class="space-y-2">
                ${(items || []).length
                    ? items.map(formatter).join('')
                    : '<div class="text-on-surface-variant font-label-mono text-[10px]">EMPTY</div>'}
            </div>
        </section>
    `;
    const taskItem = item => {
        const location = item.file_path
            ? `${item.file_path}${item.line ? `:${item.line}` : ''}`
            : '';
        return `<div class="font-label-mono text-[11px] text-on-surface break-words">- [ ] ${escapeHTML(item.text || item)} <span class="opacity-50">${escapeHTML(location)}</span></div>`;
    };
    const noteItem = item =>
        `<div class="font-label-mono text-[11px] text-on-surface break-words">${escapeHTML(item.id || item.path || '')} <span class="opacity-50">${escapeHTML(item.path || '')}</span></div>`;
    content.innerHTML = [
        section(
            `FOCUS / ${dashboard.date || ''}`,
            dashboard.focus || [],
            item => `<div class="font-label-mono text-[11px] text-primary break-words">${escapeHTML(item)}</div>`,
        ),
        section('TODAY_TASKS', dashboard.today_tasks || [], taskItem),
        section('OVERDUE_TASKS', dashboard.overdue_tasks || [], taskItem),
        section('TELEGRAM_TASKS', dashboard.telegram_tasks || [], taskItem),
        section('ORPHAN_NOTES', dashboard.orphan_notes || [], noteItem),
    ].join('');
}

async function openProjectPages() {
    if (!window.orangeBridge?.isAvailable()) return;
    openModal('project-pages-modal');
    const content = document.getElementById('project-pages-content');
    if (content) {
        content.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">BUILDING_PROJECT_PAGE_DIFFS...</div>';
    }
    try {
        projectPagesPreview = await window.orangeBridge.json('api_get_project_pages_preview');
        if (projectPagesPreview.status !== 'success') {
            throw new Error(projectPagesPreview.message || 'Project preview failed');
        }
        renderProjectPages(projectPagesPreview);
    } catch (error) {
        if (content) {
            content.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(error.toString())}</div>`;
        }
    }
}

function renderProjectPages(preview) {
    const content = document.getElementById('project-pages-content');
    if (!content) return;
    const plans = preview.plans || [];
    if (!plans.length) {
        content.innerHTML = '<div class="p-3 text-on-surface-variant font-label-mono text-[11px]">NO_PROJECT_PAGES_FOUND</div>';
        return;
    }
    content.innerHTML = plans.map((plan, index) => `
        <section class="border border-outline p-3 bg-black/30">
            <div class="flex items-center justify-between gap-3 border-b border-outline pb-2 mb-2">
                <div class="font-label-mono text-[10px] text-primary break-words">${escapeHTML(plan.relative_path || plan.path || '')}</div>
                <span class="font-label-mono text-[10px] text-on-surface-variant">PLAN_${index + 1}</span>
            </div>
            <pre class="whitespace-pre-wrap break-words text-[11px] leading-relaxed max-h-64 overflow-y-auto">${escapeHTML(plan.diff || '')}</pre>
        </section>
    `).join('');
}

async function applyProjectPages() {
    if (!window.orangeBridge?.isAvailable() || !projectPagesPreview?.preview_id) return;
    if (!confirm('Apply exactly these Project Pages diffs to the vault?')) {
        await rejectProjectPages();
        return;
    }
    try {
        const result = await window.orangeBridge.json(
            'api_apply_project_pages',
            projectPagesPreview.preview_id,
        );
        if (result.status !== 'success') {
            throw new Error(result.message || 'Apply failed');
        }
        projectPagesPreview = null;
        closeModal('project-pages-modal');
        appendMessage('Project Pages', result.message, 'sys');
        await openAuditLog();
    } catch (error) {
        appendMessage('Project Pages', `Apply failed: ${error.toString()}`, 'sys');
    }
}

async function rejectProjectPages() {
    if (window.orangeBridge?.isAvailable() && projectPagesPreview?.preview_id) {
        await window.orangeBridge.json(
            'api_reject_project_pages',
            projectPagesPreview.preview_id,
        );
    }
    projectPagesPreview = null;
    closeModal('project-pages-modal');
}

async function openWeeklyReview() {
    if (!window.orangeBridge?.isAvailable()) return;
    openModal('weekly-review-modal');
    const content = document.getElementById('weekly-review-content');
    if (content) {
        content.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">BUILDING_WEEKLY_REVIEW_DIFF...</div>';
    }
    try {
        weeklyReviewPreview = await window.orangeBridge.json('api_get_weekly_review_preview');
        if (weeklyReviewPreview.status !== 'success') {
            throw new Error(weeklyReviewPreview.message || 'Weekly preview failed');
        }
        renderWeeklyReview(weeklyReviewPreview);
    } catch (error) {
        if (content) {
            content.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(error.toString())}</div>`;
        }
    }
}

function renderWeeklyReview(preview) {
    const content = document.getElementById('weekly-review-content');
    if (!content) return;
    const plan = preview.plan || {};
    content.innerHTML = `
        <section class="border border-outline p-3 bg-black/30">
            <div class="flex items-center justify-between gap-3 border-b border-outline pb-2 mb-2">
                <div class="font-label-mono text-[10px] text-primary break-words">${escapeHTML(plan.relative_path || '')}</div>
                <span class="font-label-mono text-[10px] text-on-surface-variant">${escapeHTML(preview.week || '')}</span>
            </div>
            <pre class="whitespace-pre-wrap break-words text-[11px] leading-relaxed max-h-[54vh] overflow-y-auto">${escapeHTML(plan.diff || '')}</pre>
        </section>
    `;
}

async function applyWeeklyReview() {
    if (!window.orangeBridge?.isAvailable() || !weeklyReviewPreview?.preview_id) return;
    if (!confirm('Write exactly this Weekly Review diff to the vault?')) {
        await rejectWeeklyReview();
        return;
    }
    try {
        const result = await window.orangeBridge.json(
            'api_apply_weekly_review',
            weeklyReviewPreview.preview_id,
        );
        if (result.status !== 'success') {
            throw new Error(result.message || 'Apply failed');
        }
        weeklyReviewPreview = null;
        closeModal('weekly-review-modal');
        appendMessage('Weekly Review', result.message, 'sys');
        await openAuditLog();
    } catch (error) {
        appendMessage('Weekly Review', `Apply failed: ${error.toString()}`, 'sys');
    }
}

async function rejectWeeklyReview() {
    if (window.orangeBridge?.isAvailable() && weeklyReviewPreview?.preview_id) {
        await window.orangeBridge.json(
            'api_reject_weekly_review',
            weeklyReviewPreview.preview_id,
        );
    }
    weeklyReviewPreview = null;
    closeModal('weekly-review-modal');
}

async function openAuditLog() {
    if (!window.orangeBridge?.isAvailable()) return;
    openModal('audit-log-modal');
    const list = document.getElementById('audit-log-list');
    if (list) {
        list.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">LOADING_AUDIT_LOG...</div>';
    }
    try {
        const payload = await window.orangeBridge.json('api_get_audit_log', 300);
        if (payload.status !== 'success') {
            throw new Error(payload.message || 'Audit load failed');
        }
        renderAuditLog(payload.items || []);
    } catch (error) {
        if (list) {
            list.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(error.toString())}</div>`;
        }
    }
}

function renderAuditLog(items) {
    const list = document.getElementById('audit-log-list');
    if (!list) return;
    if (!items.length) {
        list.innerHTML = '<div class="p-3 text-on-surface-variant font-label-mono text-[11px]">NO_AUDIT_EVENTS</div>';
        return;
    }
    list.innerHTML = items.map(item => `
        <section class="border border-outline p-3 bg-black/30">
            <div class="flex flex-wrap items-center gap-2 border-b border-outline pb-2 mb-2">
                <span class="text-primary font-label-mono text-[10px]">#${escapeHTML(item.id)}</span>
                <span class="border border-primary text-primary px-2 py-0.5 font-label-mono text-[10px]">${escapeHTML(item.event_type || '')}</span>
                <span class="border border-outline text-on-surface px-2 py-0.5 font-label-mono text-[10px]">${escapeHTML(item.status || '')}</span>
                <span class="text-on-surface-variant font-label-mono text-[10px]">${escapeHTML(item.timestamp || '')}</span>
            </div>
            <div class="font-body-sm text-body-sm text-on-surface break-words mb-2">${escapeHTML(item.summary || '')}</div>
            ${item.details
                ? `<pre class="whitespace-pre-wrap break-words text-[10px] leading-relaxed max-h-40 overflow-y-auto text-on-surface-variant">${escapeHTML(item.details.slice(0, 6000))}</pre>`
                : ''}
        </section>
    `).join('');
}

async function openVaultIntelligence(mode = 'time-machine') {
    if (!window.orangeBridge?.isAvailable()) return;
    const allowedModes = new Set([
        'time-machine',
        'contradictions',
        'debate',
        'dormant',
        'manual',
    ]);
    if (!allowedModes.has(mode)) return;

    vaultIntelligenceMode = mode;
    openModal('vault-intelligence-modal');
    updateVaultIntelligenceTabs(mode);
    const body = document.getElementById('vault-intelligence-body');
    if (body) {
        body.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">BUILDING_INTELLIGENCE_REPORT...</div>';
    }

    try {
        if (mode === 'time-machine') {
            const payload = await window.orangeBridge.json('api_get_vault_time_machine', 90);
            if (payload.status !== 'success') throw new Error(payload.message || 'Time machine failed');
            renderVaultTimeMachine(payload);
        } else if (mode === 'contradictions') {
            const payload = await window.orangeBridge.json('api_find_contradictions');
            if (payload.status !== 'success') throw new Error(payload.message || 'Contradiction scan failed');
            renderContradictions(payload);
        } else if (mode === 'debate') {
            const payload = await window.orangeBridge.json('api_run_agent_debate', '');
            throw new Error(payload.message || 'Agent Debate is not configured');
        } else if (mode === 'dormant') {
            const payload = await window.orangeBridge.json('api_get_dormant_projects', 30);
            if (payload.status !== 'success') throw new Error(payload.message || 'Dormant scan failed');
            renderDormantProjects(payload);
        } else if (mode === 'manual') {
            const payload = await window.orangeBridge.json('api_get_operating_manual');
            if (payload.status !== 'success') throw new Error(payload.message || 'Manual failed');
            renderOperatingManual(payload.manual);
        }
    } catch (error) {
        if (body) {
            body.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(error.toString())}</div>`;
        }
    }
}

function updateVaultIntelligenceTabs(mode) {
    document.querySelectorAll('.intel-tab').forEach(button => {
        const active = button.getAttribute('data-intel-tab') === mode;
        button.className = active
            ? "intel-tab border border-primary text-primary px-2 py-1 font-label-mono text-[10px]"
            : "intel-tab border border-outline text-on-surface px-2 py-1 font-label-mono text-[10px]";
    });
}

function intelSection(title, bodyHtml) {
    return `
        <section class="border border-outline p-3 bg-black/30">
            <div class="font-label-caps text-label-caps text-primary border-b border-outline pb-2 mb-2">${escapeHTML(title)}</div>
            ${bodyHtml}
        </section>
    `;
}

function renderVaultTimeMachine(payload) {
    const body = document.getElementById('vault-intelligence-body');
    if (!body) return;
    const themeHtml = (payload.themes || []).map(item =>
        `<span class="border border-primary text-primary px-2 py-0.5 font-label-mono text-[10px]">${escapeHTML(item.term)}:${escapeHTML(item.count)}</span>`
    ).join(' ') || '<span class="text-on-surface-variant">NO_THEMES</span>';
    const noteRow = note =>
        `<div class="font-label-mono text-[11px] text-on-surface break-words">${escapeHTML(note.title)} <span class="opacity-50">${escapeHTML(note.path)} / ${escapeHTML(note.modified_at)}</span></div>`;
    const timelineHtml = (payload.timeline || []).map(bucket => `
        <div class="border border-outline p-2">
            <div class="font-label-mono text-[10px] text-primary mb-1">${escapeHTML(bucket.period)} / ${escapeHTML(bucket.count)} notes</div>
            <div class="space-y-1">${(bucket.notes || []).map(noteRow).join('')}</div>
        </div>
    `).join('') || '<div class="text-on-surface-variant font-label-mono text-[10px]">NO_RECENT_ACTIVITY</div>';
    body.innerHTML = `
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
            ${intelSection('SYSTEM_SNAPSHOT', `
                <div class="font-label-mono text-[11px] text-on-surface space-y-1">
                    <div>HISTORY_SOURCE: ${escapeHTML(payload.history_source || 'file_activity')}</div>
                    <div>TOTAL_NOTES: ${escapeHTML(payload.total_notes)}</div>
                    <div>RECENT_NOTES: ${escapeHTML(payload.recent_notes)}</div>
                    <div>GENERATED_AT: ${escapeHTML(payload.generated_at)}</div>
                </div>
            `)}
            ${intelSection('THEMES', `<div class="flex flex-wrap gap-1">${themeHtml}</div>`)}
            ${intelSection('TIMELINE', `<div class="space-y-2">${timelineHtml}</div>`)}
            ${intelSection('ACTIVITY_BURSTS', `<div class="space-y-1">${(payload.activity_bursts || []).map(noteRow).join('') || '<div class="text-on-surface-variant">EMPTY</div>'}</div>`)}
            ${intelSection('QUIETEST_NOTES', `<div class="space-y-1">${(payload.quietest_notes || []).map(noteRow).join('') || '<div class="text-on-surface-variant">EMPTY</div>'}</div>`)}
        </div>
    `;
}

function renderContradictions(payload) {
    const body = document.getElementById('vault-intelligence-body');
    if (!body) return;
    const rows = (payload.findings || []).map(item => `
        <section class="border border-outline p-3 bg-black/30">
            <div class="flex flex-wrap items-center gap-2 border-b border-outline pb-2 mb-2">
                <span class="border border-primary text-primary px-2 py-0.5 font-label-mono text-[10px]">${escapeHTML(item.type)}</span>
                <span class="text-on-surface-variant font-label-mono text-[10px]">SEVERITY ${escapeHTML(item.severity)}</span>
                <span class="text-on-surface-variant font-label-mono text-[10px]">CONFIDENCE ${escapeHTML(item.confidence || 'possible')}</span>
                <span class="text-primary font-label-mono text-[10px]">${escapeHTML(item.topic)}</span>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-2">
                <pre class="whitespace-pre-wrap break-words text-[11px] border border-outline p-2">${escapeHTML(JSON.stringify(item.left, null, 2))}</pre>
                <pre class="whitespace-pre-wrap break-words text-[11px] border border-outline p-2">${escapeHTML(JSON.stringify(item.right, null, 2))}</pre>
            </div>
            <div class="font-label-mono text-[11px] text-on-surface mt-2">${escapeHTML(item.suggestion || '')}</div>
        </section>
    `).join('');
    body.innerHTML = rows
        || '<div class="p-3 text-on-surface-variant font-label-mono text-[11px]">NO_CONTRADICTIONS_FOUND</div>';
}

function renderDormantProjects(payload) {
    const body = document.getElementById('vault-intelligence-body');
    if (!body) return;
    const rows = (payload.items || []).map(item => `
        <section class="border border-outline p-3 bg-black/30">
            <div class="flex flex-wrap items-center gap-2 border-b border-outline pb-2 mb-2">
                <span class="text-primary font-label-mono text-[10px]">${escapeHTML(item.title)}</span>
                <span class="border border-outline text-on-surface px-2 py-0.5 font-label-mono text-[10px]">SCORE ${escapeHTML(item.score)}</span>
                <span class="text-on-surface-variant font-label-mono text-[10px]">${escapeHTML(item.age_days)} days</span>
            </div>
            <div class="font-label-mono text-[10px] text-on-surface-variant mb-2">${escapeHTML(item.path)}</div>
            <div class="font-label-mono text-[11px] text-primary mb-2">${escapeHTML(item.revive_action)}</div>
            <div class="space-y-1">${(item.open_tasks || []).map(task =>
                `<div class="font-label-mono text-[11px] text-on-surface">- [ ] ${escapeHTML(task)}</div>`
            ).join('')}</div>
        </section>
    `).join('');
    body.innerHTML = `<div class="space-y-3">${rows
        || '<div class="p-3 text-on-surface-variant font-label-mono text-[11px]">NO_DORMANT_PROJECTS</div>'}</div>`;
}

function renderOperatingManual(manual) {
    const body = document.getElementById('vault-intelligence-body');
    if (!body) return;
    const list = items =>
        `<div class="space-y-1">${(items || []).map(item =>
            `<div class="font-label-mono text-[11px] text-on-surface break-words">- ${escapeHTML(item)}</div>`
        ).join('') || '<div class="text-on-surface-variant">EMPTY</div>'}</div>`;
    body.innerHTML = `
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
            ${intelSection('PRINCIPLES', list(manual?.principles))}
            ${intelSection('CURRENT_CONTEXT', list(manual?.current_context))}
            ${intelSection('HOW_TO_WORK_WITH_ORANGE', list(manual?.how_to_work_with_orange))}
            ${intelSection('REVIEW_RHYTHM', list(manual?.review_rhythm))}
            ${intelSection('SAFETY_CONTRACT', list(manual?.safety_contract))}
            ${intelSection('RECENT_SYSTEM_EVENTS', list(manual?.recent_system_events))}
        </div>
    `;
}
