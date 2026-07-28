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
            icon.innerText = isPinned ? "push_pin" : "terminal";

            const title = document.createElement('span');
            title.className = "flex-1 truncate cursor-text";
            title.innerText = chat.title || 'New Chat';
            title.title = "Double click to rename";
            title.ondblclick = async (event) => {
                event.stopPropagation();
                const newName = prompt("New chat name:", chat.title || '');
                if (newName && newName.trim()) {
                    await window.pywebview.api.api_rename_chat(chat.id, newName.trim());
                    refreshChatList();
                }
            };

            const pinBtn = document.createElement('span');
            pinBtn.className = "material-symbols-outlined text-[16px] opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:text-primary";
            pinBtn.innerText = "push_pin";
            pinBtn.title = isPinned ? "Unpin chat" : "Pin chat";
            pinBtn.onclick = async (event) => {
                event.stopPropagation();
                await window.pywebview.api.api_toggle_pin(chat.id);
                refreshChatList();
            };

            const deleteBtn = document.createElement('span');
            deleteBtn.className = "material-symbols-outlined text-[16px] opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:text-error text-on-surface-variant";
            deleteBtn.innerText = "delete";
            deleteBtn.title = "Delete chat";
            deleteBtn.onclick = async (event) => {
                event.stopPropagation();
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
    } catch (error) {
        console.error("Error loading chat list:", error);
    }
}

window.refreshChatList = refreshChatList;

async function searchChats(query) {
    if (!query.trim()) {
        refreshChatList();
        return;
    }
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
    } catch (error) {
        console.error('Search error:', error);
    }
}

window.searchChats = searchChats;

async function createNewChat() {
    if (!window.pywebview) return;
    try {
        currentChatId = await window.pywebview.api.api_create_chat("New Chat");
        if (container) container.innerHTML = '';
        appendMessage('System', 'New connection session initiated.', 'sys');
        refreshChatList();
    } catch (error) {
        console.error("Error creating chat:", error);
    }
}

async function loadChat(chatId) {
    if (!window.pywebview) return;
    currentChatId = chatId;
    try {
        const history = await window.pywebview.api.api_load_chat(chatId);
        if (container) container.innerHTML = '';
        if (history.length === 0) {
            appendMessage('System', 'Connection session established. Dialogue is empty.', 'sys');
        } else {
            history.forEach(msg => {
                if (msg.content && (
                    msg.content.startsWith("[Служебный системный контекст:")
                    || msg.content.startsWith("[System context:")
                    || msg.content.startsWith("[Service system context:")
                )) {
                    return;
                }
                appendMessage(
                    msg.role === 'user' ? 'User' : 'Orange',
                    msg.content,
                    msg.role === 'user' ? 'user' : 'sys',
                );
            });
        }
        refreshChatList();
    } catch (error) {
        console.error("Error loading chat details:", error);
    }
}

async function exportChat() {
    if (!currentChatId) {
        appendMessage('System', 'Error: No active chat to export.', 'sys');
        return;
    }
    appendMessage('System', 'Starting chat export...', 'sys');
    try {
        const result = await window.pywebview.api.api_export_chat();
        appendMessage('System', result, 'sys');
        if (String(result).startsWith('Успех!')) {
            const exportedPath = String(result).split(' в ').pop() || '';
            const exportedName = exportedPath.split(/[\\/]/).pop() || 'vault export';
            showToast(exportedName);
        }
    } catch (error) {
        appendMessage('System', `Error exporting chat: ${error.toString()}`, 'sys');
    }
}

async function sendToAgent() {
    if (!inputEl) return;
    const prompt = inputEl.value.trim();
    if (!prompt) return;

    appendMessage('User', prompt, 'user');
    const attachmentPaths = pendingAttachments.map(file => file.file_path);
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
        const result = await window.pywebview.api.run_agent(
            currentMode,
            prompt,
            JSON.stringify(attachmentPaths),
        );
        removeLoader();
        appendMessage('Orange', result, 'sys');
        currentChatId = await window.pywebview.api.api_get_current_chat_id();
        refreshChatList();
    } catch (error) {
        removeLoader();
        appendMessage(
            'Orange',
            `**CRITICAL KERNEL ERROR:** \n\`\`\`text\n${error.toString()}\n\`\`\``,
            'sys',
        );
    } finally {
        if (sendBtn) {
            sendBtn.disabled = false;
            sendBtn.textContent = 'INITIATE';
        }
        inputEl.focus();
        scrollToBottom();
    }
}
