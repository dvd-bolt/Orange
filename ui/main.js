// Global Application State
let currentChatId = null;
let currentMode = 'auto';
let telemetryOpen = false;
let pendingAttachments = [];
let currentTelemetrySetting = 'ON';
let currentTelegramDaemonSetting = 'OFF';
let currentAutoBackupSetting = 'OFF';
let currentAutoPushSetting = 'OFF';
let cachedHttpBaseUrl = null;
let smartInboxProposals = [];
let lastGraphData = null;
let currentGraphFilter = 'all';
let projectPagesPreview = null;
let weeklyReviewPreview = null;
let vaultIntelligenceMode = 'time-machine';

// DOM Elements
const inputEl = document.getElementById('user-input');
const container = document.getElementById('chat-canvas');
const sendBtn = document.getElementById('send-btn');

const commandPaletteCommands = [
    { id: 'new-chat', label: 'NEW_SESSION', hint: 'Create an empty chat', run: () => createNewChat() },
    { id: 'search-chats', label: 'SEARCH_CHATS', hint: 'Focus sidebar search', run: () => document.getElementById('chat-search')?.focus() },
    { id: 'export-chat', label: 'EXPORT_TO_OBSIDIAN', hint: 'Export active chat', run: () => exportChat() },
    { id: 'open-graph', label: 'OPEN_KNOWLEDGE_GRAPH', hint: 'Toggle vault graph', run: () => toggleKnowledgeGraph() },
    { id: 'morning-dashboard', label: 'MORNING_DASHBOARD', hint: 'Open daily operating view', run: () => openMorningDashboard() },
    { id: 'memory-editor', label: 'MEMORY_EDITOR', hint: 'Review pinned and RAG-excluded memory', run: () => openMemoryEditor() },
    { id: 'smart-inbox', label: 'SMART_INBOX', hint: 'Review inbox proposals', run: () => openSmartInbox() },
    { id: 'project-pages', label: 'PROJECT_PAGES', hint: 'Build project overview pages with diff preview', run: () => openProjectPages() },
    { id: 'weekly-review', label: 'WEEKLY_REVIEW', hint: 'Generate this week review with diff preview', run: () => openWeeklyReview() },
    { id: 'audit-log', label: 'AUDIT_LOG', hint: 'Open command and write history', run: () => openAuditLog() },
    { id: 'vault-time-machine', label: 'VAULT_TIME_MACHINE', hint: 'Show vault activity timeline and themes', run: () => openVaultIntelligence('time-machine') },
    { id: 'contradiction-finder', label: 'CONTRADICTION_FINDER', hint: 'Find conflicting notes and task states', run: () => openVaultIntelligence('contradictions') },
    { id: 'agent-debate', label: 'AGENT_DEBATE', hint: 'Run Engineer / Strategist / Skeptic debate', run: () => openVaultIntelligence('debate') },
    { id: 'dormant-radar', label: 'DORMANT_PROJECT_RADAR', hint: 'Find stale projects with open loops', run: () => openVaultIntelligence('dormant') },
    { id: 'operating-manual', label: 'OPERATING_MANUAL', hint: 'Build personal operating manual', run: () => openVaultIntelligence('manual') },
    { id: 'telemetry', label: 'TOGGLE_TELEMETRY', hint: 'Open or close system telemetry', run: () => toggleTelemetry() },
    { id: 'settings', label: 'OPEN_SETTINGS', hint: 'Open global settings', run: () => openSettings() },
    { id: 'backup', label: 'RUN_LOCAL_BACKUP', hint: 'Manual local vault backup', run: () => runManualBackup() },
    { id: 'vault-review', label: 'START_VAULT_REVIEW', hint: 'Ask Orange for a vault review', run: () => startVaultReview() },
];

let commandPaletteIndex = 0;

// Input Textarea Autofit & Key Listener
if (inputEl) {
    inputEl.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });
    inputEl.addEventListener('keypress', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendToAgent();
        }
    });
}

// Telemetry Toggle Logic
function toggleTelemetry() {
    const sidebar = document.getElementById('telemetry-sidebar');
    const mainContent = document.getElementById('main-content');
    
    telemetryOpen = !telemetryOpen;
    
    if (telemetryOpen) {
        sidebar.classList.remove('translate-x-full');
        sidebar.classList.add('translate-x-0');
        // If window is wide enough, push the chat content; otherwise overlay
        if (window.innerWidth >= 1200) {
            mainContent.style.marginRight = '30rem'; // 480px
        } else {
            mainContent.style.marginRight = '0';
        }
    } else {
        sidebar.classList.add('translate-x-full');
        sidebar.classList.remove('translate-x-0');
        mainContent.style.marginRight = '0';
    }
}

// Adaptive resize listener to shift margin in real-time
window.addEventListener('resize', () => {
    const mainContent = document.getElementById('main-content');
    if (mainContent) {
        if (telemetryOpen && window.innerWidth >= 1200) {
            mainContent.style.marginRight = '30rem';
        } else {
            mainContent.style.marginRight = '0';
        }
    }
});

function openCommandPalette() {
    commandPaletteIndex = 0;
    const modal = document.getElementById('command-palette-modal');
    const input = document.getElementById('command-palette-input');
    if (!modal || !input) return;
    modal.classList.remove('hidden');
    input.value = '';
    renderCommandPalette('');
    setTimeout(() => input.focus(), 0);
}

function closeCommandPalette() {
    document.getElementById('command-palette-modal')?.classList.add('hidden');
}

function renderCommandPalette(query = '') {
    const list = document.getElementById('command-palette-list');
    if (!list) return;
    const normalized = query.trim().toLowerCase();
    const matches = commandPaletteCommands.filter(cmd =>
        !normalized || cmd.label.toLowerCase().includes(normalized) || cmd.hint.toLowerCase().includes(normalized)
    );
    commandPaletteIndex = Math.min(commandPaletteIndex, Math.max(matches.length - 1, 0));
    list.innerHTML = '';
    if (!matches.length) {
        list.innerHTML = '<div class="p-3 text-on-surface-variant opacity-60">NO_MATCHES</div>';
        return;
    }
    matches.forEach((cmd, index) => {
        const row = document.createElement('button');
        row.className = index === commandPaletteIndex
            ? "w-full text-left p-3 border-l-2 border-primary bg-primary bg-opacity-10 text-primary flex flex-col gap-1"
            : "w-full text-left p-3 text-on-surface hover:text-primary hover:bg-surface-variant flex flex-col gap-1";
        row.innerHTML = `<span>${escapeHTML(cmd.label)}</span><span class="text-[10px] opacity-60">${escapeHTML(cmd.hint)}</span>`;
        row.onclick = () => executeCommand(cmd);
        list.appendChild(row);
    });
}

function getVisibleCommandMatches() {
    const input = document.getElementById('command-palette-input');
    const normalized = (input?.value || '').trim().toLowerCase();
    return commandPaletteCommands.filter(cmd =>
        !normalized || cmd.label.toLowerCase().includes(normalized) || cmd.hint.toLowerCase().includes(normalized)
    );
}

function executeCommand(cmd) {
    closeCommandPalette();
    cmd.run();
}

function handleCommandPaletteKey(event) {
    const matches = getVisibleCommandMatches();
    if (event.key === 'Escape') {
        event.preventDefault();
        closeCommandPalette();
    } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        commandPaletteIndex = Math.min(commandPaletteIndex + 1, Math.max(matches.length - 1, 0));
        renderCommandPalette(event.target.value);
    } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        commandPaletteIndex = Math.max(commandPaletteIndex - 1, 0);
        renderCommandPalette(event.target.value);
    } else if (event.key === 'Enter' && matches.length) {
        event.preventDefault();
        executeCommand(matches[commandPaletteIndex]);
    }
}

function startVaultReview() {
    const input = document.getElementById('user-input');
    if (!input) return;
    input.value = 'Проведи краткое ревью Obsidian vault: найди незавершенные задачи, заметки без связей и предложи 3 главных следующих шага.';
    input.style.height = 'auto';
    input.style.height = input.scrollHeight + 'px';
    input.focus();
}

window.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        openCommandPalette();
    }
});

// Toast Notification Logic
function showToast(fileName = 'vault export') {
    const toast = document.getElementById('toast-notification');
    if (toast) {
        const fileSyncText = toast.querySelector('.animate-pulse');
        if (fileSyncText) {
            fileSyncText.textContent = `[+] FILE_SYNCED: ${fileName}`;
        }
        toast.classList.remove('hidden');
        toast.classList.add('toast-enter');
        
        setTimeout(() => {
            toast.classList.add('hidden');
            toast.classList.remove('toast-enter');
        }, 3000);
    }
}

// Scroll to bottom helper
function scrollToBottom() {
    if (container) {
        setTimeout(() => {
            container.scrollTop = container.scrollHeight;
        }, 50);
    }
}

// Modal Windows Management
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('hidden');
    }
}

// Ensure closing by clicking on close button works correctly
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('hidden');
    }
}

function openPanic() {
    openModal('system-panic-modal');
}

function closePanic() {
    closeModal('system-panic-modal');
}

// Set mode (Auto, Base, Deep Research, Coder)
function setMode(mode) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.remove('bg-primary', 'text-on-primary-container');
        btn.classList.add('text-on-background', 'hover:text-primary', 'hover:border-primary');
        if (btn.id === 'mode-coder') {
            btn.className = "mode-btn font-label-caps text-label-caps text-on-background hover:text-primary hover:border-primary border border-transparent px-4 py-2 transition-colors relative hover:z-10 hover:ring-1 hover:ring-primary hover:bg-transparent";
        } else {
            btn.className = "mode-btn font-label-caps text-label-caps text-on-background hover:text-primary hover:border-primary border border-transparent border-r-outline px-4 py-2 transition-colors relative hover:z-10 hover:ring-1 hover:ring-primary hover:bg-transparent";
        }
    });
    
    const activeBtn = document.getElementById('mode-' + mode);
    if (activeBtn) {
        if (mode === 'coder') {
            activeBtn.className = "mode-btn font-label-caps text-label-caps bg-primary text-on-primary-container px-4 py-2 relative z-10";
        } else {
            activeBtn.className = "mode-btn font-label-caps text-label-caps bg-primary text-on-primary-container px-4 py-2 border-r border-outline relative z-10";
        }
    }
}

// File uploading integration
let pendingPdfPath = null;

async function uploadFile() {
    if (!window.pywebview) return;
    showLoader();
    try {
        const resultStr = await window.pywebview.api.api_stage_file();
        removeLoader();
        const result = JSON.parse(resultStr);
        if (result.status === 'success') {
            pendingAttachments.push({
                filename: result.filename,
                file_path: result.file_path
            });
            renderAttachmentChips();
        } else if (result.status === 'pdf_config_needed') {
            // PDF — show range config modal
            pendingPdfPath = result.file_path;
            const filenameEl = document.getElementById('pdf-config-filename');
            if (filenameEl) filenameEl.textContent = `SOURCE: ${result.filename} (${result.page_count} pgs)`;
            const pageCountEl = document.getElementById('pdf-page-count');
            if (pageCountEl) pageCountEl.value = result.page_count;
            openModal('attachment-config-modal');
        } else if (result.status === 'cancelled') {
            // Cancelled by user
        } else {
            appendMessage('System', `Error importing document: ${result.message}`, 'sys');
        }
    } catch (e) {
        removeLoader();
        appendMessage('System', `Failed to import document: ${e.toString()}`, 'sys');
    }
}

async function confirmPdfAttachment() {
    const allPagesCheck = document.getElementById('pdf-extract-all');
    const allPages = allPagesCheck ? allPagesCheck.checked : true;
    const pageCountEl = document.getElementById('pdf-page-count');
    const totalPages = pageCountEl ? parseInt(pageCountEl.value) || 1 : 1;
    let startPage = 1, endPage = totalPages;
    if (!allPages) {
        const rangeInput = document.getElementById('pdf-range-input');
        if (rangeInput && rangeInput.value.trim()) {
            const match = rangeInput.value.trim().match(/^(\d+)-(\d+)$/);
            if (match) { startPage = parseInt(match[1]); endPage = parseInt(match[2]); }
        }
    }
    closeModal('attachment-config-modal');
    if (!pendingPdfPath) return;
    showLoader();
    try {
        const res = JSON.parse(await window.pywebview.api.api_stage_pdf_with_range(pendingPdfPath, startPage, endPage));
        removeLoader();
        if (res.status === 'success') {
            pendingAttachments.push({ filename: res.filename, file_path: res.file_path });
            renderAttachmentChips();
        } else {
            appendMessage('System', `PDF extraction error: ${res.message}`, 'sys');
        }
    } catch(e) {
        removeLoader();
        appendMessage('System', `PDF failure: ${e}`, 'sys');
    }
    pendingPdfPath = null;
}
window.confirmPdfAttachment = confirmPdfAttachment;

async function cancelPdfAttachment() {
    const stagedPath = pendingPdfPath;
    pendingPdfPath = null;
    closeModal('attachment-config-modal');
    if (stagedPath && window.orangeBridge?.isAvailable()) {
        try {
            await window.orangeBridge.call('api_discard_staged_attachment', stagedPath);
        } catch (_error) {
            // Stale files are also removed by the backend TTL cleanup.
        }
    }
}
window.cancelPdfAttachment = cancelPdfAttachment;

function renderAttachmentChips() {
    const container = document.getElementById('attachment-chips-container');
    if (!container) return;
    container.innerHTML = '';
    pendingAttachments.forEach((file, index) => {
        const chip = document.createElement('div');
        chip.className = "flex items-center gap-2 px-2 py-1 border border-primary text-primary font-label-mono text-[10px] bg-primary bg-opacity-5";
        chip.innerHTML = `
            <span>[ ${escapeHTML(file.filename)} ]</span>
            <button onclick="removeAttachment(${index})" class="hover:text-white transition-colors cursor-pointer ml-1 font-bold">✕</button>
        `;
        container.appendChild(chip);
    });
}

async function removeAttachment(index) {
    const attachment = pendingAttachments[index];
    pendingAttachments.splice(index, 1);
    renderAttachmentChips();
    if (attachment?.file_path && window.orangeBridge?.isAvailable()) {
        try {
            await window.orangeBridge.call('api_discard_staged_attachment', attachment.file_path);
        } catch (_error) {
            // Stale files are also removed by the backend TTL cleanup.
        }
    }
}

window.removeAttachment = removeAttachment;

// Append Chat Message
function appendMessage(sender, text, type = 'sys') {
    if (!container) return;
    const wrapper = document.createElement('div');
    
    if (type === 'sys') {
        // System / Agent message style
        if (sender === 'System') {
            wrapper.className = "font-label-mono text-label-mono text-primary flex items-center gap-2 max-w-4xl self-center w-full justify-center opacity-80";
            wrapper.innerHTML = `<span class="material-symbols-outlined text-[14px]">info</span><span>System: ${escapeHTML(text)}</span>`;
        } else {
            const safeMarkdown = renderSafeMarkdown(text);
            wrapper.className = "border border-primary p-4 max-w-4xl self-start w-full bg-primary bg-opacity-[0.02]";
            wrapper.innerHTML = `
                <div class="font-label-caps text-label-caps text-primary mb-4 uppercase border-b border-outline pb-2 flex items-center gap-2">
                    <span class="w-2 h-2 bg-primary"></span>
                    AGENT_RESPONSE
                </div>
                <div class="font-body-lg text-body-lg text-on-background space-y-4 markdown-body">
                    ${safeMarkdown}
                </div>
            `;
            
            // Inject Copy Buttons into pre elements
            const preElements = wrapper.querySelectorAll('pre');
            preElements.forEach(pre => {
                pre.classList.add('relative', 'group');
                
                const codeEl = pre.querySelector('code');
                const codeText = codeEl ? codeEl.innerText : pre.innerText;
                
                const copyBtn = document.createElement('button');
                copyBtn.className = "absolute top-2 right-2 px-2 py-1 bg-[#000000] border border-outline hover:border-primary text-primary font-label-mono text-[10px] opacity-0 group-hover:opacity-100 transition-opacity duration-150 rounded-none z-10 cursor-pointer hover:bg-primary hover:text-on-primary-container";
                copyBtn.innerText = "[ COPY ]";
                
                copyBtn.onclick = async () => {
                    try {
                        if (navigator.clipboard && navigator.clipboard.writeText) {
                            await navigator.clipboard.writeText(codeText);
                        } else {
                            const textArea = document.createElement("textarea");
                            textArea.value = codeText;
                            textArea.style.position = "fixed";
                            document.body.appendChild(textArea);
                            textArea.focus();
                            textArea.select();
                            document.execCommand('copy');
                            document.body.removeChild(textArea);
                        }
                        copyBtn.innerText = "[ COPIED ]";
                        setTimeout(() => {
                            copyBtn.innerText = "[ COPY ]";
                        }, 2000);
                    } catch (err) {
                        console.error('Failed to copy text: ', err);
                    }
                };
                
                pre.appendChild(copyBtn);

                const codeLanguage = codeEl?.className || '';
                if (/\blanguage-python\b/i.test(codeLanguage)) {
                    copyBtn.classList.remove('right-2');
                    copyBtn.style.right = '5.5rem';
                    const executeBtn = document.createElement('button');
                    executeBtn.className = "absolute top-2 right-2 px-2 py-1 bg-[#000000] border border-primary text-primary font-label-mono text-[10px] opacity-0 group-hover:opacity-100 transition-opacity duration-150 rounded-none z-10 cursor-pointer hover:bg-primary hover:text-on-primary-container";
                    executeBtn.innerText = "[ EXECUTE ]";
                    executeBtn.title = "Run with explicit approval";
                    executeBtn.onclick = () => executeCodeWithApproval(codeText);
                    pre.appendChild(executeBtn);
                }
            });
        }
    } else {
        // User message style
        wrapper.className = "border border-on-background p-4 max-w-4xl self-end w-full";
        wrapper.innerHTML = `
            <div class="font-label-caps text-label-caps text-on-background mb-4 uppercase border-b border-outline pb-2 inline-block">USER_DIRECTIVE</div>
            <div class="font-body-lg text-body-lg text-on-background">
                ${escapeHTML(text)}
            </div>
        `;
    }
    
    container.appendChild(wrapper);
    scrollToBottom();
}

function escapeHTML(str) {
    return String(str).replace(/[&<>'"]/g,
        tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
}

function renderSafeMarkdown(text) {
    if (!window.marked || !window.DOMPurify) {
        return `<div class="whitespace-pre-wrap break-words">${escapeHTML(text)}</div>`;
    }
    const rawMarkdown = window.marked.parse(String(text), {
        async: false,
        breaks: true,
    });
    return window.DOMPurify.sanitize(rawMarkdown, {
        USE_PROFILES: { html: true },
    });
}

async function getHttpBaseUrl() {
    if (cachedHttpBaseUrl) return cachedHttpBaseUrl;
    if (window.orangeBridge?.isAvailable()) {
        try {
            if (typeof window.pywebview?.api?.api_get_http_base_url === 'function') {
                cachedHttpBaseUrl = await window.orangeBridge.call('api_get_http_base_url');
                return cachedHttpBaseUrl;
            }
            const status = await window.orangeBridge.json('api_get_system_status');
            cachedHttpBaseUrl = status.http_base_url || `http://127.0.0.1:${status.orange_port || 8080}`;
            return cachedHttpBaseUrl;
        } catch (error) {
            console.error('HTTP base URL discovery failed:', error);
        }
    }
    return 'http://127.0.0.1:8080';
}

// Show/Remove Loader
function showLoader() {
    if (!container) return;
    const loader = document.createElement('div');
    loader.id = 'active-loader';
    loader.className = "border border-primary p-4 max-w-4xl self-start w-full border-dashed";
    loader.innerHTML = `
        <div class="flex items-center gap-3 font-label-mono text-label-mono text-primary">
            <span class="material-symbols-outlined text-[16px] animate-spin">sync</span>
            <span class="animate-blink">CORE_PROCESSING_SEQ...</span>
        </div>
    `;
    container.appendChild(loader);
    scrollToBottom();
}

function removeLoader() {
    const loader = document.getElementById('active-loader');
    if (loader) loader.remove();
}

// System Panic & Command Override
function triggerSystemPanic(errorText) {
    const textEl = document.getElementById('system-panic-text');
    if (textEl) {
        textEl.innerText = errorText;
    }
    const modal = document.getElementById('system-panic-modal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.style.zIndex = '999999';
    }
}

function showExecutionOverride(commandText) {
    const container = document.getElementById('execution-command-container');
    if (container) {
        container.innerText = commandText;
    }
    const modal = document.getElementById('execution-override-modal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.style.zIndex = '99999';
    }
}

function handleOverrideResponse(approved) {
    closeModal('execution-override-modal');
    if (window.pywebview) {
        window.pywebview.api.api_handle_override_response(approved);
    }
}

// Telemetry Log Injection (called from Python via evaluate_js)
function addTelemetryLog(timestamp, logType, message) {
    const sidebar = document.getElementById('telemetry-sidebar');
    if (!sidebar) return;
    
    const logContainer = sidebar.querySelector('.overflow-y-auto');
    if (!logContainer) return;
    document.getElementById('telemetry-empty-state')?.remove();
    
    // Determine color scheme based on log type
    let typeColorClass, typeBorderClass, typeBgClass, textColorClass;
    switch (logType) {
        case 'OK':
        case 'CONN':
            typeColorClass = 'text-[#00FF66]';
            typeBorderClass = 'border-[#00FF66]/20';
            typeBgClass = 'bg-[#00FF66]/5';
            textColorClass = 'text-white/95';
            break;
        case 'FAIL':
        case 'CRITICAL':
            typeColorClass = 'text-red-500';
            typeBorderClass = 'border-red-500/20';
            typeBgClass = 'bg-red-500/5';
            textColorClass = 'text-red-200/95';
            break;
        case 'WARN':
            typeColorClass = 'text-yellow-500';
            typeBorderClass = 'border-yellow-500/20';
            typeBgClass = 'bg-yellow-500/5';
            textColorClass = 'text-yellow-200/95';
            break;
        default: // EXEC, TG, MEM, etc.
            typeColorClass = 'text-primary';
            typeBorderClass = 'border-primary/20';
            typeBgClass = 'bg-primary/5';
            textColorClass = 'text-white/95';
            break;
    }
    
    const row = document.createElement('div');
    row.className = 'flex gap-3 telemetry-log-row items-start';
    row.innerHTML = `
        <span class="text-primary/50 font-mono text-[10px] pt-0.5 shrink-0">[${escapeHTML(timestamp)}]</span>
        <span class="${typeColorClass} border ${typeBorderClass} ${typeBgClass} px-1 py-0.2 text-[9px] font-bold tracking-widest shrink-0">${escapeHTML(logType)}</span>
        <span class="${textColorClass} flex-1 font-mono text-xs break-words">${escapeHTML(message)}</span>
    `;
    
    // Insert before the last "AWAITING" row, or at the end
    const awaitingRow = logContainer.querySelector('.animate-pulse');
    if (awaitingRow && awaitingRow.closest('.telemetry-log-row')) {
        logContainer.insertBefore(row, awaitingRow.closest('.telemetry-log-row'));
    } else {
        logContainer.appendChild(row);
    }
    
    // Auto-scroll telemetry
    logContainer.scrollTop = logContainer.scrollHeight;
}

// Inline code execution is a direct, approval-gated Bridge call.
async function executeCodeWithApproval(code) {
    appendMessage('System', 'Running code in the restricted executor...', 'sys');
    showLoader();
    try {
        if (!window.pywebview || !window.pywebview.api.api_execute_python) {
            throw new Error('Restricted executor is not available');
        }
        const result = await window.pywebview.api.api_execute_python(code);
        removeLoader();
        appendMessage('Orange [Executor]', result, 'sys');
    } catch(e) {
        removeLoader();
        appendMessage('Orange', `Error: ${e}`, 'sys');
    }
}
window.executeCodeWithApproval = executeCodeWithApproval;

// Exporting functions to global window context
window.openSettings = openSettings;
window.closeSettings = closeSettings;
window.saveSettings = saveSettings;
window.updateTelemetrySettingsUI = updateTelemetrySettingsUI;
window.triggerSystemPanic = triggerSystemPanic;
window.showExecutionOverride = showExecutionOverride;
window.handleOverrideResponse = handleOverrideResponse;
window.addTelemetryLog = addTelemetryLog;
window.updateTelegramDaemonUI = updateTelegramDaemonUI;
window.updateAutoBackupUI = updateAutoBackupUI;
window.updateAutoPushUI = updateAutoPushUI;
window.runManualBackup = runManualBackup;
window.exportChat = exportChat;
window.createNewChat = createNewChat;
window.loadChat = loadChat;
window.uploadFile = uploadFile;
window.setMode = setMode;
window.toggleTelemetry = toggleTelemetry;
window.openCommandPalette = openCommandPalette;
window.closeCommandPalette = closeCommandPalette;
window.renderCommandPalette = renderCommandPalette;
window.handleCommandPaletteKey = handleCommandPaletteKey;
window.openMemoryEditor = openMemoryEditor;
window.toggleMemoryFlag = toggleMemoryFlag;
window.deleteMemoryItem = deleteMemoryItem;
window.openSmartInbox = openSmartInbox;
window.addSmartInboxProposal = addSmartInboxProposal;
window.applyInboxProposalByIndex = applyInboxProposalByIndex;
window.openMorningDashboard = openMorningDashboard;
window.openProjectPages = openProjectPages;
window.applyProjectPages = applyProjectPages;
window.rejectProjectPages = rejectProjectPages;
window.openWeeklyReview = openWeeklyReview;
window.applyWeeklyReview = applyWeeklyReview;
window.rejectWeeklyReview = rejectWeeklyReview;
window.openAuditLog = openAuditLog;
window.openVaultIntelligence = openVaultIntelligence;

// Localization dynamic switcher
let i18nData = null;

async function switchLanguage(lang, persist = true) {
    if (!window.orangeBridge?.isAvailable() || !['ru', 'en'].includes(lang)) return;
    try {
        if (!i18nData) {
            const i18nStr = await window.orangeBridge.call('api_get_i18n');
            i18nData = JSON.parse(i18nStr);
        }
        const dict = i18nData[lang];
        if (!dict) return;

        // Apply text translations
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (dict[key]) {
                el.textContent = dict[key];
            }
        });

        // Apply placeholder translations
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            if (dict[key]) {
                el.setAttribute('placeholder', dict[key]);
            }
        });

        if (persist) {
            await window.orangeBridge.call('set_language', lang);
        }
    } catch(e) {
        console.error("Error switching language:", e);
    }
}
window.switchLanguage = switchLanguage;

// Initialize Application UI
async function initUI() {
    if(!window.pywebview) {
        setTimeout(initUI, 100);
        return;
    }
    refreshChatList();

    // Load settings language and apply (default to Russian)
    let lang = 'ru';
    try {
        const settingsStr = await window.pywebview.api.api_get_settings();
        const settings = JSON.parse(settingsStr);
        if (settings && settings.language) {
            lang = settings.language;
        }
    } catch(e) {
        console.error("Error initializing language settings:", e);
    }
    
    await switchLanguage(lang, false);
    const langToggle = document.getElementById('language-toggle');
    if (langToggle) {
        langToggle.value = lang;
    }
    openMorningDashboard();
}

// Run on page load
document.addEventListener('DOMContentLoaded', () => {
    // Initial UI bind for textarea
    const tx = document.getElementsByTagName("textarea");
    for (let i = 0; i < tx.length; i++) {
        tx[i].setAttribute("style", "height:" + (tx[i].scrollHeight) + "px;overflow-y:hidden;");
    }
    initUI();
});

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

async function toggleVoiceRecording() {
    const micIcon = document.getElementById('voice-record-icon');
    const micBtn = document.getElementById('voice-record-btn');
    if (!micIcon || !micBtn) return;
    
    if (!isRecording) {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioChunks = [];
            
            let options = { mimeType: 'audio/webm' };
            if (!MediaRecorder.isTypeSupported(options.mimeType)) {
                options = { mimeType: 'audio/ogg' };
            }
            if (!MediaRecorder.isTypeSupported(options.mimeType)) {
                options = {};
            }
            
            mediaRecorder = new MediaRecorder(stream, options);
            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };
            
            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
                stream.getTracks().forEach(track => track.stop());
                
                const reader = new FileReader();
                reader.readAsDataURL(audioBlob);
                reader.onloadend = async () => {
                    const base64Data = reader.result.split(',')[1];
                    micBtn.title = "TRANSCRIBING...";
                    micIcon.innerText = "pending";
                    try {
                        const text = await window.pywebview.api.api_transcribe_audio(
                            base64Data,
                            audioBlob.type || 'audio/webm'
                        );
                        const inputEl = document.getElementById('user-input');
                        if (inputEl && text && !String(text).startsWith('[')) {
                            inputEl.value = (inputEl.value ? inputEl.value + " " : "") + text;
                            inputEl.style.height = 'auto';
                            inputEl.style.height = inputEl.scrollHeight + 'px';
                        } else if (text) {
                            appendMessage('System', text, 'sys');
                        }
                    } catch(e) {
                        console.error("Transcription error:", e);
                    } finally {
                        micBtn.title = "Record Voice Directive";
                        micIcon.innerText = "mic";
                    }
                };
            };
            
            mediaRecorder.start();
            isRecording = true;
            micIcon.innerText = "stop";
            micIcon.classList.add("text-error");
            micBtn.title = "Stop Recording";
        } catch(e) {
            console.error("Mic access denied:", e);
            alert("Не удалось получить доступ к микрофону: " + e.toString());
        }
    } else {
        if (mediaRecorder && mediaRecorder.state !== "inactive") {
            mediaRecorder.stop();
        }
        isRecording = false;
        micIcon.classList.remove("text-error");
    }
}
window.toggleVoiceRecording = toggleVoiceRecording;
