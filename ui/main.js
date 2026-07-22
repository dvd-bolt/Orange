// Tailwind Custom Configuration
tailwind.config = {
    darkMode: "class",
    theme: {
        extend: {
            "colors": {
                "primary-fixed-dim": "#ffb596",
                "error-container": "#93000a",
                "outline-variant": "#5a4136",
                "secondary-fixed-dim": "#c6c6c7",
                "on-surface": "#e2e2e2",
                "on-error-container": "#ffdad6",
                "secondary": "#c6c6c7",
                "on-primary-fixed": "#360f00",
                "surface-container-high": "#2a2a2a",
                "surface-container-low": "#1b1b1b",
                "surface-tint": "#ffb596",
                "surface-container-highest": "#353535",
                "on-tertiary-container": "#2f2f2f",
                "surface-dim": "#131313",
                "background": "#000000",
                "primary-container": "#ff6600",
                "inverse-surface": "#e2e2e2",
                "on-primary-fixed-variant": "#7c2e00",
                "on-background": "#e2e2e2",
                "on-secondary-fixed": "#1a1c1c",
                "on-secondary-fixed-variant": "#454747",
                "inverse-on-surface": "#303030",
                "on-primary-container": "#000000",
                "outline": "#262626",
                "on-primary": "#581e00",
                "surface": "#000000",
                "primary": "#ff6600",
                "tertiary": "#c8c6c5",
                "on-secondary-container": "#b4b5b5",
                "surface-container-lowest": "#0e0e0e",
                "on-surface-variant": "#e3bfb1",
                "surface-variant": "#262626",
                "surface-container": "#1f1f1f",
                "secondary-container": "#454747",
                "on-secondary": "#2f3131",
                "tertiary-fixed": "#e4e2e1",
                "on-tertiary-fixed-variant": "#474746",
                "inverse-primary": "#a33e00",
                "tertiary-container": "#989696",
                "error": "#ffb4ab",
                "surface-bright": "#393939",
                "on-error": "#690005",
                "secondary-fixed": "#e2e2e2",
                "on-tertiary-fixed": "#1b1c1c",
                "tertiary-fixed-dim": "#c8c6c5",
                "primary-fixed": "#ffdbcd",
                "on-tertiary": "#303030"
            },
            "borderRadius": {
                "DEFAULT": "0px",
                "lg": "0px",
                "xl": "0px",
                "full": "0px"
            },
            "spacing": {
                "stack-md": "1.5rem",
                "gutter": "1rem",
                "margin-page": "2rem",
                "stack-sm": "0.5rem",
                "sidebar-width": "288px"
            },
            "fontFamily": {
                "body-lg": ["JetBrains Mono"],
                "label-caps": ["JetBrains Mono"],
                "label-mono": ["JetBrains Mono"],
                "headline-md": ["JetBrains Mono"],
                "headline-lg": ["JetBrains Mono"],
                "body-sm": ["JetBrains Mono"]
            },
            "fontSize": {
                "body-lg": ["16px", { "lineHeight": "24px", "letterSpacing": "0em", "fontWeight": "400" }],
                "label-caps": ["12px", { "lineHeight": "16px", "letterSpacing": "0.15em", "fontWeight": "800" }],
                "label-mono": ["11px", { "lineHeight": "14px", "letterSpacing": "0.05em", "fontWeight": "500" }],
                "headline-md": ["24px", { "lineHeight": "32px", "letterSpacing": "-0.01em", "fontWeight": "700" }],
                "headline-lg": ["32px", { "lineHeight": "40px", "letterSpacing": "-0.02em", "fontWeight": "700" }],
                "body-sm": ["14px", { "lineHeight": "20px", "letterSpacing": "0em", "fontWeight": "400" }]
            }
        },
    },
};

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
function showToast(fileName = 'log_export_v4.md') {
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

function removeAttachment(index) {
    pendingAttachments.splice(index, 1);
    renderAttachmentChips();
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
            const rawMarkdown = marked.parse(text);
            const safeMarkdown = window.DOMPurify ? DOMPurify.sanitize(rawMarkdown) : escapeHTML(rawMarkdown);
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

async function getHttpBaseUrl() {
    if (cachedHttpBaseUrl) return cachedHttpBaseUrl;
    if (window.pywebview) {
        try {
            if (window.pywebview.api.api_get_http_base_url) {
                cachedHttpBaseUrl = await window.pywebview.api.api_get_http_base_url();
                return cachedHttpBaseUrl;
            }
            const res = await window.pywebview.api.api_get_system_status();
            const status = JSON.parse(res);
            cachedHttpBaseUrl = status.http_base_url || `http://127.0.0.1:${status.orange_port || 8080}`;
            return cachedHttpBaseUrl;
        } catch(e) {
            console.error('HTTP base URL discovery failed:', e);
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

// Refresh chats sidebar list
async function refreshChatList() {
    if (!window.pywebview) return;
    try {
        const chats = await window.pywebview.api.api_get_chats();
        const listEl = document.getElementById('chat-list');
        if (!listEl) return;
        listEl.innerHTML = '';
        chats.forEach(chat => {
            const isPinned = chat.is_pinned === 1 || chat.is_pinned === true;
            const isActive = chat.id === currentChatId;
            
            const item = document.createElement('button');
            item.className = isActive 
                ? "w-full text-left font-label-mono text-label-mono text-on-primary-container bg-primary-container bg-opacity-20 border-l-2 border-primary px-4 py-3 flex items-center gap-3 group relative" 
                : "w-full text-left font-label-mono text-label-mono text-on-surface hover:text-primary px-4 py-3 hover:bg-surface-variant flex items-center gap-3 transition-colors group relative";
            item.onclick = () => loadChat(chat.id);
            
            const icon = document.createElement('span');
            icon.className = "material-symbols-outlined text-[16px]";
            icon.innerText = "terminal";
            
            const title = document.createElement('span');
            title.className = "flex-1 truncate cursor-text";
            title.innerText = (isPinned ? '📌 ' : '') + (chat.title || 'New Chat');
            title.title = "Double click to rename";
            title.ondblclick = async (e) => {
                e.stopPropagation();
                const newName = prompt("New chat name:", chat.title || '');
                if (newName && newName.trim()) {
                    await window.pywebview.api.api_rename_chat(chat.id, newName.trim());
                    refreshChatList();
                }
            };

            const pinBtn = document.createElement('span');
            pinBtn.className = "opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:text-primary";
            pinBtn.innerText = "📌";
            pinBtn.onclick = async (e) => {
                e.stopPropagation();
                await window.pywebview.api.api_toggle_pin(chat.id);
                refreshChatList();
            };

            const deleteBtn = document.createElement('span');
            deleteBtn.className = "opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:text-error ml-1 text-on-surface-variant text-xs font-bold";
            deleteBtn.innerText = "✕";
            deleteBtn.title = "Delete Chat";
            deleteBtn.onclick = async (e) => {
                e.stopPropagation();
                if (!confirm(`Delete chat "${chat.title || 'New Chat'}"?`)) return;
                await window.pywebview.api.api_delete_chat(chat.id);
                if (chat.id === currentChatId) {
                    currentChatId = null;
                    if (container) container.innerHTML = '';
                    appendMessage('System', 'Chat deleted. Create a new session.', 'sys');
                }
                refreshChatList();
            };

            item.appendChild(icon);
            item.appendChild(title);
            item.appendChild(pinBtn);
            item.appendChild(deleteBtn);
            listEl.appendChild(item);
        });
    } catch (e) {
        console.error("Error loading chat list: ", e);
    }
}

window.refreshChatList = refreshChatList;

// Фича 9: Поиск по чатам
async function searchChats(query) {
    if (!query.trim()) { refreshChatList(); return; }
    if (!window.pywebview) return;
    try {
        const results = await window.pywebview.api.api_search_chats(query);
        const listEl = document.getElementById('chat-list');
        if (!listEl) return;
        listEl.innerHTML = '';
        if (!results.length) {
            listEl.innerHTML = '<div class="px-4 py-3 font-label-mono text-[11px] text-on-surface opacity-40">No results found</div>';
            return;
        }
        results.forEach(msg => {
            const item = document.createElement('button');
            item.className = "w-full text-left font-label-mono text-[11px] text-on-surface hover:text-primary px-4 py-3 hover:bg-surface-variant flex flex-col gap-1 transition-colors";
            item.onclick = () => loadChat(msg.chat_id);
            item.innerHTML = `
                <span class="text-primary text-[10px] truncate">${escapeHTML(msg.title || 'Untitled')}</span>
                <span class="text-[10px] opacity-60 truncate">${escapeHTML((msg.content || '').substring(0, 60))}...</span>
            `;
            listEl.appendChild(item);
        });
    } catch(e) { console.error('Search error:', e); }
}
window.searchChats = searchChats;

// Create new chat session
async function createNewChat() {
    if (!window.pywebview) return;
    try {
        currentChatId = await window.pywebview.api.api_create_chat("New Chat");
        if (container) container.innerHTML = '';
        appendMessage('System', 'New connection session initiated.', 'sys');
        refreshChatList();
    } catch (e) {
        console.error("Error creating chat: ", e);
    }
}

// Load existing chat session
async function loadChat(chatId) {
    if (!window.pywebview) return;
    currentChatId = chatId;
    try {
        const history = await window.pywebview.api.api_load_chat(chatId);
        if (container) container.innerHTML = '';
        if(history.length === 0) {
            appendMessage('System', 'Connection session established. Dialogue is empty.', 'sys');
        } else {
            history.forEach(msg => {
                if (msg.content && (msg.content.startsWith("[Служебный системный контекст:") || msg.content.startsWith("[System context:") || msg.content.startsWith("[Service system context:"))) {
                    return;
                }
                if(msg.role === 'user') {
                    appendMessage('User', msg.content, 'user');
                } else {
                    appendMessage('Orange', msg.content, 'sys');
                }
            });
        }
        refreshChatList();
    } catch (e) {
        console.error("Error loading chat details: ", e);
    }
}

// Export Chat to Markdown
async function exportChat() {
    if(!currentChatId) {
        appendMessage('System', 'Error: No active chat to export.', 'sys');
        return;
    }
    appendMessage('System', 'Starting chat export...', 'sys');
    try {
        const result = await window.pywebview.api.api_export_chat();
        appendMessage('System', result, 'sys');
        showToast();
    } catch(e) {
        appendMessage('System', `Error exporting chat: ${e.toString()}`, 'sys');
    }
}

// Send Command / Message to Agent
async function sendToAgent() {
    if (!inputEl) return;
    const prompt = inputEl.value.trim();
    if(!prompt) return;

    const profile = currentMode;
    appendMessage('User', prompt, 'user');
    
    const attachmentPaths = pendingAttachments.map(f => f.file_path);
    pendingAttachments = [];
    renderAttachmentChips();
    
    inputEl.value = '';
    inputEl.style.height = '48px';
    
    if (sendBtn) {
        sendBtn.disabled = true;
        sendBtn.textContent = 'PROCESSING...';
    }
    showLoader();

    try {
        const result = await window.pywebview.api.run_agent(profile, prompt, JSON.stringify(attachmentPaths));
        removeLoader();
        appendMessage('Orange', result, 'sys');
        currentChatId = await window.pywebview.api.api_get_current_chat_id();
        refreshChatList();
    } catch(e) {
        removeLoader();
        appendMessage('Orange', `**CRITICAL KERNEL ERROR:** \n\`\`\`text\n${e.toString()}\n\`\`\``, 'sys');
    } finally {
        if (sendBtn) {
            sendBtn.disabled = false;
            sendBtn.textContent = 'INITIATE';
        }
        inputEl.focus();
        scrollToBottom();
    }
}

// Global Settings Management
async function openSettings() {
    if (!window.pywebview) return;
    try {
        const settingsStr = await window.pywebview.api.api_get_settings();
        const settings = JSON.parse(settingsStr);
        
        if (settings.status === 'error') {
            appendMessage('System', `Failed to load settings: ${settings.message}`, 'sys');
            return;
        }
        
        const tokenInput = document.getElementById('setting-auth-token');
        if (tokenInput) {
            tokenInput.value = settings.auth_token || '';
        }
        
        updateTelemetrySettingsUI(settings.telemetry_stream || 'ON');
        updateTelegramDaemonUI(settings.telegram_daemon || 'OFF');
        updateAutoBackupUI(settings.auto_backup_enabled || 'OFF');
        updateAutoPushUI(settings.auto_push_enabled || 'OFF');
        
        openModal('settings-modal');
    } catch (e) {
        console.error("Error opening settings: ", e);
    }
}

function closeSettings() {
    closeModal('settings-modal');
}

// Фича 3: Переключение вкладок настроек
function switchSettingsTab(tabName) {
    ['api', 'paths', 'demons'].forEach(t => {
        document.getElementById(`settings-panel-${t}`)?.classList.add('hidden');
        const btn = document.getElementById(`tab-${t}`);
        if (btn) btn.className = "text-on-surface-variant font-label-mono text-label-mono hover:text-primary cursor-pointer";
    });
    document.getElementById(`settings-panel-${tabName}`)?.classList.remove('hidden');
    const activeBtn = document.getElementById(`tab-${tabName}`);
    if (activeBtn) activeBtn.className = "text-primary font-label-mono text-label-mono border-b border-primary pb-0.5 cursor-pointer";
    // Загружаем актуальные статусы при переходе на системные вкладки
    if ((tabName === 'paths' || tabName === 'demons') && window.pywebview) {
        window.pywebview.api.api_get_system_status().then(res => {
            const s = JSON.parse(res);
            const vaultEl = document.getElementById('status-vault-path');
            const portEl = document.getElementById('status-orange-port');
            const mcpEl = document.getElementById('status-mcp');
            if (vaultEl) vaultEl.textContent = s.obsidian_vault_path;
            if (portEl) portEl.textContent = s.http_base_url || `:${s.orange_port}`;
            if (mcpEl) mcpEl.textContent = s.mcp_status;
        }).catch(err => console.error('System status error:', err));
    }
}
window.switchSettingsTab = switchSettingsTab;

// Фича 4: MCP Dashboard с реальными статусами
async function openMCPDashboard() {
    if (window.pywebview) {
        try {
            const res = await window.pywebview.api.api_get_mcp_status();
            const s = JSON.parse(res);
            const sqlEl = document.querySelector('#mcp-dashboard-modal [data-mcp="sqlite-status"]');
            const mcpEl = document.querySelector('#mcp-dashboard-modal [data-mcp="mcp-status"]');
            if (sqlEl) sqlEl.textContent = `${s.sqlite.status} (${s.sqlite.size_mb} MB)`;
            if (mcpEl) mcpEl.textContent = s.mcp.status;
        } catch(e) { console.error('MCP status error:', e); }
    }
    openModal('mcp-dashboard-modal');
}
window.openMCPDashboard = openMCPDashboard;

async function saveSettings() {
    if (!window.pywebview) return;
    try {
        const tokenInput = document.getElementById('setting-auth-token');
        const tokenValue = tokenInput ? tokenInput.value : '';
        const langToggle = document.getElementById('language-toggle');
        const langValue = langToggle ? langToggle.value : 'en';
        
        const settings = {
            auth_token: tokenValue,
            telemetry_stream: currentTelemetrySetting,
            telegram_daemon: currentTelegramDaemonSetting,
            auto_backup_enabled: currentAutoBackupSetting,
            auto_push_enabled: currentAutoPushSetting,
            language: langValue
        };
        
        const resultStr = await window.pywebview.api.api_save_settings(settings);
        const result = JSON.parse(resultStr);
        if (result.status === 'success') {
            closeSettings();
            appendMessage('System', 'Settings saved successfully.', 'sys');
        } else {
            appendMessage('System', `Error saving settings: ${result.message}`, 'sys');
        }
    } catch (e) {
        console.error("Error saving settings: ", e);
        appendMessage('System', `Failed to save settings: ${e.toString()}`, 'sys');
    }
}

function updateTelemetrySettingsUI(state) {
    currentTelemetrySetting = state;
    const btnOn = document.getElementById('btn-telemetry-on');
    const btnOff = document.getElementById('btn-telemetry-off');
    if (btnOn && btnOff) {
        if (state === 'ON') {
            btnOn.className = "px-3 py-1 bg-primary text-on-primary text-[10px] font-bold";
            btnOff.className = "px-3 py-1 text-on-surface text-[10px]";
        } else {
            btnOn.className = "px-3 py-1 text-on-surface text-[10px]";
            btnOff.className = "px-3 py-1 bg-primary text-on-primary text-[10px] font-bold";
        }
    }
}

function updateTelegramDaemonUI(state) {
    currentTelegramDaemonSetting = state;
    const btnOn = document.getElementById('btn-tgdaemon-on');
    const btnOff = document.getElementById('btn-tgdaemon-off');
    if (btnOn && btnOff) {
        if (state === 'ON') {
            btnOn.className = "px-3 py-1 bg-primary text-on-primary text-[10px] font-bold";
            btnOff.className = "px-3 py-1 text-on-surface text-[10px]";
        } else {
            btnOn.className = "px-3 py-1 text-on-surface text-[10px]";
            btnOff.className = "px-3 py-1 bg-primary text-on-primary text-[10px] font-bold";
        }
    }
}

function updateAutoBackupUI(state) {
    currentAutoBackupSetting = state;
    const btnOn = document.getElementById('btn-autobackup-on');
    const btnOff = document.getElementById('btn-autobackup-off');
    if (btnOn && btnOff) {
        if (state === 'ON') {
            btnOn.className = "px-3 py-1 bg-primary text-on-primary text-[10px] font-bold";
            btnOff.className = "px-3 py-1 text-on-surface text-[10px]";
        } else {
            btnOn.className = "px-3 py-1 text-on-surface text-[10px]";
            btnOff.className = "px-3 py-1 bg-primary text-on-primary text-[10px] font-bold";
        }
    }
}

function updateAutoPushUI(state) {
    currentAutoPushSetting = state;
    const btnOn = document.getElementById('btn-autopush-on');
    const btnOff = document.getElementById('btn-autopush-off');
    if (btnOn && btnOff) {
        if (state === 'ON') {
            btnOn.className = "px-3 py-1 bg-primary text-on-primary text-[10px] font-bold";
            btnOff.className = "px-3 py-1 text-on-surface text-[10px]";
        } else {
            btnOn.className = "px-3 py-1 text-on-surface text-[10px]";
            btnOff.className = "px-3 py-1 bg-primary text-on-primary text-[10px] font-bold";
        }
    }
}

async function runManualBackup() {
    if (!window.pywebview) return;
    appendMessage('System', 'Starting local vault backup...', 'sys');
    try {
        const result = JSON.parse(await window.pywebview.api.api_run_git_backup());
        appendMessage('System', `${result.status}: ${result.message}`, 'sys');
    } catch(e) {
        appendMessage('System', `Backup failed: ${e.toString()}`, 'sys');
    }
}

async function openMemoryEditor() {
    if (!window.pywebview) return;
    openModal('memory-editor-modal');
    const list = document.getElementById('memory-editor-list');
    if (list) list.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">LOADING_MEMORY...</div>';
    try {
        const payload = JSON.parse(await window.pywebview.api.api_get_memory_items(300));
        if (payload.status !== 'success') throw new Error(payload.message || 'Memory load failed');
        renderMemoryEditor(payload.items || []);
    } catch(e) {
        if (list) list.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(e.toString())}</div>`;
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
    if (!window.pywebview) return;
    const isPinned = flag === 'pin' ? value : null;
    const excludeFromRag = flag === 'rag' ? value : null;
    try {
        const payload = JSON.parse(await window.pywebview.api.api_update_memory_item(messageId, isPinned, excludeFromRag));
        if (payload.status !== 'success') throw new Error(payload.message || 'Update failed');
        await openMemoryEditor();
    } catch(e) {
        appendMessage('System', `Memory update failed: ${e.toString()}`, 'sys');
    }
}

async function deleteMemoryItem(messageId) {
    if (!window.pywebview || !confirm('Delete this memory item?')) return;
    try {
        const payload = JSON.parse(await window.pywebview.api.api_delete_memory_item(messageId));
        if (payload.status !== 'success') throw new Error(payload.message || 'Delete failed');
        await openMemoryEditor();
    } catch(e) {
        appendMessage('System', `Memory delete failed: ${e.toString()}`, 'sys');
    }
}

async function openSmartInbox() {
    if (!window.pywebview) return;
    openModal('smart-inbox-modal');
    const list = document.getElementById('smart-inbox-list');
    if (list) list.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">SCANNING_INBOX...</div>';
    try {
        const payload = JSON.parse(await window.pywebview.api.api_get_inbox_proposals());
        if (payload.status !== 'success') throw new Error(payload.message || 'Inbox scan failed');
        smartInboxProposals = payload.items || [];
        renderSmartInbox();
    } catch(e) {
        if (list) list.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(e.toString())}</div>`;
    }
}

function addSmartInboxProposal(proposal) {
    const key = proposal.file_path || proposal.relative_path || proposal.filename;
    smartInboxProposals = smartInboxProposals.filter(item => (item.file_path || item.relative_path || item.filename) !== key);
    smartInboxProposals.unshift(proposal);
    appendMessage('Smart Inbox', `Proposal: ${(proposal.category || 'note').toUpperCase()} / ${proposal.filename || key}`, 'sys');
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
            row.innerHTML = `
                <div class="flex items-center justify-between gap-3">
                    <div class="min-w-0">
                        <div class="font-label-mono text-[10px] text-primary truncate">${escapeHTML(item.filename || '')}</div>
                        <div class="font-label-mono text-[10px] text-on-surface-variant">${escapeHTML(item.relative_path || item.file_path || '')}</div>
                    </div>
                    <span class="border border-primary text-primary px-2 py-1 font-label-mono text-[10px] shrink-0">${escapeHTML((item.category || 'idea').toUpperCase())}</span>
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
    applyInboxProposal(item.file_path || '', item.category || '');
}

async function applyInboxProposal(filePath, category) {
    if (!window.pywebview || !confirm('Apply this Smart Inbox proposal?')) return;
    try {
        const payload = JSON.parse(await window.pywebview.api.api_apply_inbox_proposal(filePath, category));
        if (payload.status !== 'success') throw new Error(payload.message || 'Apply failed');
        appendMessage('Smart Inbox', payload.message, 'sys');
        await openSmartInbox();
    } catch(e) {
        appendMessage('Smart Inbox', `Apply failed: ${e.toString()}`, 'sys');
    }
}

async function openMorningDashboard() {
    if (!window.pywebview) return;
    openModal('morning-dashboard-modal');
    const content = document.getElementById('morning-dashboard-content');
    if (content) content.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">BUILDING_DASHBOARD...</div>';
    try {
        const payload = JSON.parse(await window.pywebview.api.api_get_morning_dashboard());
        if (payload.status !== 'success') throw new Error(payload.message || 'Dashboard failed');
        renderMorningDashboard(payload.dashboard);
    } catch(e) {
        if (content) content.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(e.toString())}</div>`;
    }
}

function renderMorningDashboard(dashboard) {
    const content = document.getElementById('morning-dashboard-content');
    if (!content) return;
    const section = (title, items, formatter) => `
        <section class="border border-outline p-3 bg-black/30 min-h-[120px]">
            <div class="font-label-caps text-label-caps text-primary border-b border-outline pb-2 mb-2">${escapeHTML(title)}</div>
            <div class="space-y-2">
                ${(items || []).length ? items.map(formatter).join('') : '<div class="text-on-surface-variant font-label-mono text-[10px]">EMPTY</div>'}
            </div>
        </section>
    `;
    const taskItem = item => `<div class="font-label-mono text-[11px] text-on-surface break-words">- [ ] ${escapeHTML(item.text || item)} <span class="opacity-50">${escapeHTML(item.file_path || '')}</span></div>`;
    const noteItem = item => `<div class="font-label-mono text-[11px] text-on-surface break-words">${escapeHTML(item.id || item.path || '')} <span class="opacity-50">${escapeHTML(item.path || '')}</span></div>`;
    content.innerHTML = [
        section(`FOCUS / ${dashboard.date || ''}`, dashboard.focus || [], item => `<div class="font-label-mono text-[11px] text-primary break-words">${escapeHTML(item)}</div>`),
        section('TODAY_TASKS', dashboard.today_tasks || [], taskItem),
        section('OVERDUE_TASKS', dashboard.overdue_tasks || [], taskItem),
        section('TELEGRAM_TASKS', dashboard.telegram_tasks || [], taskItem),
        section('ORPHAN_NOTES', dashboard.orphan_notes || [], noteItem),
    ].join('');
}

async function openProjectPages() {
    if (!window.pywebview) return;
    openModal('project-pages-modal');
    const content = document.getElementById('project-pages-content');
    if (content) content.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">BUILDING_PROJECT_PAGE_DIFFS...</div>';
    try {
        projectPagesPreview = JSON.parse(await window.pywebview.api.api_get_project_pages_preview());
        if (projectPagesPreview.status !== 'success') throw new Error(projectPagesPreview.message || 'Project preview failed');
        renderProjectPages(projectPagesPreview);
    } catch(e) {
        if (content) content.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(e.toString())}</div>`;
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
    if (!window.pywebview || !confirm('Apply generated Project Pages to vault?')) return;
    try {
        const result = JSON.parse(await window.pywebview.api.api_apply_project_pages());
        if (result.status !== 'success') throw new Error(result.message || 'Apply failed');
        closeModal('project-pages-modal');
        appendMessage('Project Pages', result.message, 'sys');
        await openAuditLog();
    } catch(e) {
        appendMessage('Project Pages', `Apply failed: ${e.toString()}`, 'sys');
    }
}

async function openWeeklyReview() {
    if (!window.pywebview) return;
    openModal('weekly-review-modal');
    const content = document.getElementById('weekly-review-content');
    if (content) content.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">BUILDING_WEEKLY_REVIEW_DIFF...</div>';
    try {
        weeklyReviewPreview = JSON.parse(await window.pywebview.api.api_get_weekly_review_preview());
        if (weeklyReviewPreview.status !== 'success') throw new Error(weeklyReviewPreview.message || 'Weekly preview failed');
        renderWeeklyReview(weeklyReviewPreview);
    } catch(e) {
        if (content) content.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(e.toString())}</div>`;
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
    if (!window.pywebview || !confirm('Write this Weekly Review to vault?')) return;
    try {
        const result = JSON.parse(await window.pywebview.api.api_apply_weekly_review());
        if (result.status !== 'success') throw new Error(result.message || 'Apply failed');
        closeModal('weekly-review-modal');
        appendMessage('Weekly Review', result.message, 'sys');
        await openAuditLog();
    } catch(e) {
        appendMessage('Weekly Review', `Apply failed: ${e.toString()}`, 'sys');
    }
}

async function openAuditLog() {
    if (!window.pywebview) return;
    openModal('audit-log-modal');
    const list = document.getElementById('audit-log-list');
    if (list) list.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">LOADING_AUDIT_LOG...</div>';
    try {
        const payload = JSON.parse(await window.pywebview.api.api_get_audit_log(300));
        if (payload.status !== 'success') throw new Error(payload.message || 'Audit load failed');
        renderAuditLog(payload.items || []);
    } catch(e) {
        if (list) list.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(e.toString())}</div>`;
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
            ${item.details ? `<pre class="whitespace-pre-wrap break-words text-[10px] leading-relaxed max-h-40 overflow-y-auto text-on-surface-variant">${escapeHTML(item.details.slice(0, 6000))}</pre>` : ''}
        </section>
    `).join('');
}

async function openVaultIntelligence(mode = 'time-machine') {
    if (!window.pywebview) return;
    vaultIntelligenceMode = mode;
    openModal('vault-intelligence-modal');
    updateVaultIntelligenceTabs(mode);
    const body = document.getElementById('vault-intelligence-body');
    if (body) body.innerHTML = '<div class="p-3 text-primary font-label-mono text-[11px]">BUILDING_INTELLIGENCE_REPORT...</div>';

    try {
        if (mode === 'time-machine') {
            const payload = JSON.parse(await window.pywebview.api.api_get_vault_time_machine(90));
            if (payload.status !== 'success') throw new Error(payload.message || 'Time machine failed');
            renderVaultTimeMachine(payload);
        } else if (mode === 'contradictions') {
            const payload = JSON.parse(await window.pywebview.api.api_find_contradictions());
            if (payload.status !== 'success') throw new Error(payload.message || 'Contradiction scan failed');
            renderContradictions(payload);
        } else if (mode === 'debate') {
            const topic = document.getElementById('agent-debate-topic')?.value || '';
            const payload = JSON.parse(await window.pywebview.api.api_run_agent_debate(topic));
            if (payload.status !== 'success') throw new Error(payload.message || 'Debate failed');
            renderAgentDebate(payload);
        } else if (mode === 'dormant') {
            const payload = JSON.parse(await window.pywebview.api.api_get_dormant_projects(30));
            if (payload.status !== 'success') throw new Error(payload.message || 'Dormant scan failed');
            renderDormantProjects(payload);
        } else if (mode === 'manual') {
            const payload = JSON.parse(await window.pywebview.api.api_get_operating_manual());
            if (payload.status !== 'success') throw new Error(payload.message || 'Manual failed');
            renderOperatingManual(payload.manual);
        }
    } catch(e) {
        if (body) body.innerHTML = `<div class="p-3 text-error font-label-mono text-[11px]">${escapeHTML(e.toString())}</div>`;
    }
}

function updateVaultIntelligenceTabs(mode) {
    document.querySelectorAll('.intel-tab').forEach(btn => {
        const active = btn.getAttribute('data-intel-tab') === mode;
        btn.className = active
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
    const noteRow = note => `<div class="font-label-mono text-[11px] text-on-surface break-words">${escapeHTML(note.title)} <span class="opacity-50">${escapeHTML(note.path)} / ${escapeHTML(note.modified_at)}</span></div>`;
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
                <span class="text-primary font-label-mono text-[10px]">${escapeHTML(item.topic)}</span>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-2">
                <pre class="whitespace-pre-wrap break-words text-[11px] border border-outline p-2">${escapeHTML(JSON.stringify(item.left, null, 2))}</pre>
                <pre class="whitespace-pre-wrap break-words text-[11px] border border-outline p-2">${escapeHTML(JSON.stringify(item.right, null, 2))}</pre>
            </div>
            <div class="font-label-mono text-[11px] text-on-surface mt-2">${escapeHTML(item.suggestion || '')}</div>
        </section>
    `).join('');
    body.innerHTML = rows || '<div class="p-3 text-on-surface-variant font-label-mono text-[11px]">NO_CONTRADICTIONS_FOUND</div>';
}

function renderAgentDebate(payload) {
    const body = document.getElementById('vault-intelligence-body');
    if (!body) return;
    const context = (payload.context_notes || []).map(note =>
        `<div class="font-label-mono text-[10px] text-on-surface break-words">${escapeHTML(note.title)} <span class="opacity-50">${escapeHTML(note.path)}</span></div>`
    ).join('');
    const rounds = (payload.rounds || []).map(round => intelSection(round.role, `
        <div class="font-label-mono text-[11px] text-primary mb-2">${escapeHTML(round.stance)}</div>
        <div class="space-y-1">${(round.points || []).map(point => `<div class="font-label-mono text-[11px] text-on-surface">- ${escapeHTML(point)}</div>`).join('')}</div>
    `)).join('');
    body.innerHTML = `
        <div class="flex gap-2 mb-3">
            <input id="agent-debate-topic" class="flex-1 bg-transparent border border-outline text-on-surface font-label-mono text-[11px] px-3 py-2 focus:border-primary focus:ring-0 outline-none" value="${escapeHTML(payload.topic || '')}" placeholder="debate topic"/>
            <button onclick="runVaultDebate()" class="border border-primary text-primary hover:bg-primary hover:text-on-primary px-3 py-2 font-label-mono text-[10px]">RUN</button>
        </div>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-3">${rounds}</div>
        ${intelSection('SYNTHESIS', `
            <div class="font-label-mono text-[11px] text-primary mb-2">${escapeHTML(payload.synthesis?.decision || '')}</div>
            <div class="space-y-1">${(payload.synthesis?.next_actions || []).map(action => `<div class="font-label-mono text-[11px] text-on-surface">- ${escapeHTML(action)}</div>`).join('')}</div>
        `)}
        ${intelSection('CONTEXT_NOTES', `<div class="space-y-1">${context || '<div class="text-on-surface-variant">EMPTY</div>'}</div>`)}
    `;
}

function runVaultDebate() {
    openVaultIntelligence('debate');
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
            <div class="space-y-1">${(item.open_tasks || []).map(task => `<div class="font-label-mono text-[11px] text-on-surface">- [ ] ${escapeHTML(task)}</div>`).join('')}</div>
        </section>
    `).join('');
    body.innerHTML = `<div class="space-y-3">${rows || '<div class="p-3 text-on-surface-variant font-label-mono text-[11px]">NO_DORMANT_PROJECTS</div>'}</div>`;
}

function renderOperatingManual(manual) {
    const body = document.getElementById('vault-intelligence-body');
    if (!body) return;
    const list = items => `<div class="space-y-1">${(items || []).map(item => `<div class="font-label-mono text-[11px] text-on-surface break-words">- ${escapeHTML(item)}</div>`).join('') || '<div class="text-on-surface-variant">EMPTY</div>'}</div>`;
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

// Фича 6: Inline Assets Execute — запуск кода из модала через агент
async function executeCodeFromModal(code) {
    closeModal('inline-assets-modal');
    appendMessage('System', 'Running code in sandbox...', 'sys');
    showLoader();
    try {
        const result = await window.pywebview.api.run_agent('coder',
            `Run this code via execute_python and show the output:\n\`\`\`python\n${code}\n\`\`\``, "[]");
        removeLoader();
        appendMessage('Orange [Coder]', result, 'sys');
        currentChatId = await window.pywebview.api.api_get_current_chat_id();
        refreshChatList();
    } catch(e) {
        removeLoader();
        appendMessage('Orange', `Error: ${e}`, 'sys');
    }
}
window.executeCodeFromModal = executeCodeFromModal;

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
window.openWeeklyReview = openWeeklyReview;
window.applyWeeklyReview = applyWeeklyReview;
window.openAuditLog = openAuditLog;
window.openVaultIntelligence = openVaultIntelligence;
window.runVaultDebate = runVaultDebate;

// Localization dynamic switcher
let i18nData = null;

async function switchLanguage(lang) {
    if (!window.pywebview) return;
    try {
        if (!i18nData) {
            const i18nStr = await window.pywebview.api.api_get_i18n();
            i18nData = JSON.parse(i18nStr);
        }
        const dict = i18nData[lang];
        if (!dict) return;

        // Apply text translations
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (dict[key]) {
                el.innerHTML = dict[key];
            }
        });

        // Apply placeholder translations
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            if (dict[key]) {
                el.setAttribute('placeholder', dict[key]);
            }
        });

        // Sync with backend config
        await window.pywebview.api.set_language(lang);
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
    
    await switchLanguage(lang);
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

// --- KNOWLEDGE GRAPH VISUALIZATION & VOICE TRANSCRIPTION ---

let isGraphVisible = false;
async function toggleKnowledgeGraph() {
    const overlay = document.getElementById('knowledge-graph-overlay');
    if (!overlay) return;
    
    isGraphVisible = !isGraphVisible;
    if (isGraphVisible) {
        overlay.classList.remove('hidden');
        await loadAndRenderGraph();
    } else {
        overlay.classList.add('hidden');
    }
}
window.toggleKnowledgeGraph = toggleKnowledgeGraph;

function setGraphFilter(filter) {
    currentGraphFilter = filter;
    document.querySelectorAll('.graph-filter-btn').forEach(btn => {
        const active = btn.getAttribute('data-graph-filter') === filter;
        btn.className = active
            ? "graph-filter-btn border border-primary text-primary px-2 py-1 font-label-mono text-[10px]"
            : "graph-filter-btn border border-outline text-on-surface px-2 py-1 font-label-mono text-[10px]";
    });
    if (lastGraphData) {
        const container = document.getElementById('graph-svg-container');
        if (container) {
            container.innerHTML = '';
            renderGraph(getFilteredGraphData(lastGraphData), container);
        }
    }
}
window.setGraphFilter = setGraphFilter;

function graphEndpointId(endpoint) {
    return typeof endpoint === 'object' ? endpoint.id : endpoint;
}

function getFilteredGraphData(data) {
    const nodes = (data.nodes || []).filter(node => {
        if (currentGraphFilter === 'orphan') return Boolean(node.orphan);
        if (currentGraphFilter === 'project') return node.type === 'project';
        if (currentGraphFilter === 'inbox') return node.type === 'inbox';
        return true;
    }).map(node => ({ ...node }));
    const nodeIds = new Set(nodes.map(node => node.id));
    const links = (data.links || []).map(link => ({
        source: graphEndpointId(link.source),
        target: graphEndpointId(link.target),
        value: link.value || 1
    })).filter(link => nodeIds.has(link.source) && nodeIds.has(link.target));
    return { nodes, links };
}

async function loadAndRenderGraph() {
    const container = document.getElementById('graph-svg-container');
    if (!container) return;
    container.innerHTML = '<div class="absolute inset-0 flex items-center justify-center text-primary font-label-mono">LOADING_GRAPH_DATA...</div>';
    
    try {
        const baseUrl = await getHttpBaseUrl();
        const response = await fetch(`${baseUrl}/api/graph`);
        const data = await response.json();
        lastGraphData = data;
        
        container.innerHTML = '';
        renderGraph(getFilteredGraphData(data), container);
    } catch(e) {
        container.innerHTML = `<div class="absolute inset-0 flex items-center justify-center text-error font-label-mono">ERROR_LOADING_GRAPH: ${e.toString()}</div>`;
    }
}

function renderGraph(data, container) {
    const width = container.clientWidth;
    const height = container.clientHeight;
    if (!data.nodes.length) {
        container.innerHTML = '<div class="absolute inset-0 flex items-center justify-center text-on-surface-variant font-label-mono">NO_GRAPH_NODES_FOR_FILTER</div>';
        return;
    }
    
    const svg = d3.create("svg")
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("viewBox", [0, 0, width, height])
        .attr("style", "max-width: 100%; height: auto;");
        
    const g = svg.append("g");
    svg.call(d3.zoom().on("zoom", (event) => {
        g.attr("transform", event.transform);
    }));
    
    const simulation = d3.forceSimulation(data.nodes)
        .force("link", d3.forceLink(data.links).id(d => d.id).distance(80))
        .force("charge", d3.forceManyBody().strength(-120))
        .force("center", d3.forceCenter(width / 2, height / 2));
        
    const link = g.append("g")
        .attr("stroke", "#262626")
        .attr("stroke-opacity", 0.6)
        .selectAll("line")
        .data(data.links)
        .join("line")
        .attr("stroke-width", 1.5);
        
    const colorScale = d3.scaleOrdinal()
        .domain([1, 2, 3])
        .range(["#E65100", "#00C853", "#00B0FF"]);
        
    const node = g.append("g")
        .attr("stroke", "#121212")
        .attr("stroke-width", 1.5)
        .selectAll("circle")
        .data(data.nodes)
        .join("circle")
        .attr("r", d => d.group === 2 ? 8 : (d.group === 3 ? 6 : (d.orphan ? 4 : 5)))
        .attr("fill", d => colorScale(d.group))
        .attr("opacity", d => d.orphan ? 0.72 : 1)
        .style("cursor", "pointer")
        .on("click", (event, d) => {
            event.stopPropagation();
            showGraphNotePreview(d);
        })
        .call(d3.drag()
            .on("start", dragstarted)
            .on("drag", dragged)
            .on("end", dragended));
            
    const label = g.append("g")
        .selectAll("text")
        .data(data.nodes)
        .join("text")
        .attr("dx", 10)
        .attr("dy", ".35em")
        .attr("font-family", "JetBrains Mono, monospace")
        .attr("font-size", "8px")
        .attr("fill", "#A3A3A3")
        .text(d => d.id);
        
    node.append("title").text(d => d.id);
        
    simulation.on("tick", () => {
        link
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);

        node
            .attr("cx", d => d.x)
            .attr("cy", d => d.y);
            
        label
            .attr("x", d => d.x)
            .attr("y", d => d.y);
    });
    
    function dragstarted(event, d) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }
    
    function dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }
    
    function dragended(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }
    
    container.appendChild(svg.node());
}

async function showGraphNotePreview(nodeData) {
    const preview = document.getElementById('graph-note-preview');
    const content = document.getElementById('graph-note-preview-content');
    if (!preview || !content) return;
    preview.classList.remove('hidden');
    content.innerHTML = '<div class="text-primary">LOADING_NOTE...</div>';
    try {
        const baseUrl = await getHttpBaseUrl();
        const response = await fetch(`${baseUrl}/api/note?path=${encodeURIComponent(nodeData.path || '')}`);
        const note = await response.json();
        if (!response.ok) throw new Error(note.error || 'Note load failed');
        const suggestions = (note.suggested_links || []).map(link =>
            `<span class="border border-primary text-primary px-2 py-0.5">${escapeHTML(`[[${link}]]`)}</span>`
        ).join(' ');
        content.innerHTML = `
            <div class="space-y-1 border-b border-outline pb-3">
                <div class="text-primary font-label-caps text-label-caps break-words">${escapeHTML(note.title || nodeData.id)}</div>
                <div class="text-on-surface-variant break-words">${escapeHTML(note.path || nodeData.path || '')}</div>
                <div class="text-on-surface-variant">DEGREE: ${escapeHTML(note.degree || 0)} / TYPE: ${escapeHTML(note.type || 'note')}</div>
            </div>
            <div>
                <div class="text-primary font-label-mono text-[10px] mb-2">SUGGESTED_WIKILINKS</div>
                <div class="flex flex-wrap gap-1">${suggestions || '<span class="text-on-surface-variant">NONE</span>'}</div>
            </div>
            <pre class="whitespace-pre-wrap break-words text-[11px] leading-relaxed border border-outline p-3 max-h-[420px] overflow-y-auto">${escapeHTML(note.content || '')}</pre>
        `;
    } catch(e) {
        content.innerHTML = `<div class="text-error break-words">${escapeHTML(e.toString())}</div>`;
    }
}

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
                        const text = await window.pywebview.api.api_transcribe_audio(base64Data);
                        const inputEl = document.getElementById('user-input');
                        if (inputEl && text) {
                            inputEl.value = (inputEl.value ? inputEl.value + " " : "") + text;
                            inputEl.style.height = 'auto';
                            inputEl.style.height = inputEl.scrollHeight + 'px';
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
