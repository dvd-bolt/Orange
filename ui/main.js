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
async function uploadFile() {
    if (!window.pywebview) return;
    showLoader();
    try {
        const resultStr = await window.pywebview.api.api_upload_file();
        removeLoader();
        const result = JSON.parse(resultStr);
        if (result.status === 'success') {
            appendMessage('Система', `Документ **${result.filename}** загружен и интегрирован в контекст чата.`, 'sys');
        } else if (result.status === 'cancelled') {
            // Cancelled by user
        } else {
            appendMessage('Система', `Ошибка импорта документа: ${result.message}`, 'sys');
        }
    } catch (e) {
        removeLoader();
        appendMessage('Система', `Сбой импорта документа: ${e.toString()}`, 'sys');
    }
}

// Append Chat Message
function appendMessage(sender, text, type = 'sys') {
    if (!container) return;
    const wrapper = document.createElement('div');
    
    if (type === 'sys') {
        // System / Agent message style
        if (sender === 'Система') {
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
            title.className = "flex-1 truncate";
            title.innerText = (isPinned ? '📌 ' : '') + (chat.title || 'Новый диалог');
            
            const pinBtn = document.createElement('span');
            pinBtn.className = "opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:text-primary";
            pinBtn.innerText = "📌";
            pinBtn.onclick = async (e) => {
                e.stopPropagation();
                await window.pywebview.api.api_toggle_pin(chat.id);
                refreshChatList();
            };
            
            item.appendChild(icon);
            item.appendChild(title);
            item.appendChild(pinBtn);
            listEl.appendChild(item);
        });
    } catch (e) {
        console.error("Error loading chat list: ", e);
    }
}

window.refreshChatList = refreshChatList;

// Create new chat session
async function createNewChat() {
    if (!window.pywebview) return;
    try {
        currentChatId = await window.pywebview.api.api_create_chat("Новый диалог");
        if (container) container.innerHTML = '';
        appendMessage('Система', 'Инициирован новый сеанс связи.', 'sys');
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
            appendMessage('Система', 'Сеанс связи установлен. Диалог пуст.', 'sys');
        } else {
            history.forEach(msg => {
                if (msg.content && msg.content.startsWith("[Служебный системный контекст:")) {
                    return;
                }
                if(msg.role === 'user') {
                    appendMessage('Пользователь', msg.content, 'user');
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
        appendMessage('Система', 'Ошибка: Нет активного чата для экспорта.', 'sys');
        return;
    }
    appendMessage('Система', 'Начинаю экспорт чата...', 'sys');
    try {
        const result = await window.pywebview.api.api_export_chat();
        appendMessage('Система', result, 'sys');
        showToast();
    } catch(e) {
        appendMessage('Система', `Ошибка при экспорте чата: ${e.toString()}`, 'sys');
    }
}

// Send Command / Message to Agent
async function sendToAgent() {
    if (!inputEl) return;
    const prompt = inputEl.value.trim();
    if(!prompt) return;

    const profile = currentMode;
    appendMessage('Пользователь', prompt, 'user');
    inputEl.value = '';
    inputEl.style.height = '48px';
    
    if (sendBtn) {
        sendBtn.disabled = true;
        sendBtn.textContent = 'PROCESSING...';
    }
    showLoader();

    try {
        const result = await window.pywebview.api.run_agent(profile, prompt);
        removeLoader();
        appendMessage('Orange', result, 'sys');
        refreshChatList();
    } catch(e) {
        removeLoader();
        appendMessage('Orange', `**CRITICAL KERNEL ERROR:** \n\`\`\`text\n${e.toString()}\n\`\`\``, 'sys');
    } finally {
        if (sendBtn) {
            sendBtn.disabled = false;
            sendBtn.textContent = 'ИНИЦИИРОВАТЬ';
        }
        inputEl.focus();
        scrollToBottom();
    }
}

// Initialize Application UI
function initUI() {
    if(!window.pywebview) {
        setTimeout(initUI, 100);
        return;
    }
    refreshChatList();
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
