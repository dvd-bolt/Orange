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

// DOM Elements
const inputEl = document.getElementById('user-input');
const container = document.getElementById('chat-canvas');
const sendBtn = document.getElementById('send-btn');

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
            wrapper.innerHTML = `<span class="material-symbols-outlined text-[14px]">info</span><span>System: ${text}</span>`;
        } else {
            wrapper.className = "border border-primary p-4 max-w-4xl self-start w-full bg-primary bg-opacity-[0.02]";
            wrapper.innerHTML = `
                <div class="font-label-caps text-label-caps text-primary mb-4 uppercase border-b border-outline pb-2 flex items-center gap-2">
                    <span class="w-2 h-2 bg-primary"></span>
                    AGENT_RESPONSE
                </div>
                <div class="font-body-lg text-body-lg text-on-background space-y-4 markdown-body">
                    ${marked.parse(text)}
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
    return str.replace(/[&<>'"]/g, 
        tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
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
            if (portEl) portEl.textContent = `:${s.orange_port}`;
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
window.exportChat = exportChat;
window.createNewChat = createNewChat;
window.loadChat = loadChat;
window.uploadFile = uploadFile;
window.setMode = setMode;
window.toggleTelemetry = toggleTelemetry;

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

    // Load settings language and apply
    try {
        const settingsStr = await window.pywebview.api.api_get_settings();
        const settings = JSON.parse(settingsStr);
        if (settings && settings.language) {
            await switchLanguage(settings.language);
            const langToggle = document.getElementById('language-toggle');
            if (langToggle) {
                langToggle.value = settings.language;
            }
        }
    } catch(e) {
        console.error("Error initializing language settings:", e);
    }
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
