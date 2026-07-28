async function openSettings() {
    if (!window.orangeBridge?.isAvailable()) return;
    try {
        const settings = await window.orangeBridge.json('api_get_settings');
        if (settings.status === 'error') {
            appendMessage('System', `Failed to load settings: ${settings.message}`, 'sys');
            return;
        }

        updateTelemetrySettingsUI(settings.telemetry_stream || 'ON');
        updateTelegramDaemonUI(settings.telegram_daemon || 'OFF');
        updateAutoBackupUI(settings.auto_backup_enabled || 'OFF');
        updateAutoPushUI(settings.auto_push_enabled || 'OFF');
        const languageToggle = document.getElementById('language-toggle');
        if (languageToggle) languageToggle.value = settings.language || 'ru';

        const status = await window.orangeBridge.json('api_get_system_status');
        const googleStatus = document.getElementById('status-google-api');
        const openRouterStatus = document.getElementById('status-openrouter-api');
        const telegramStatus = document.getElementById('status-telegram');
        if (googleStatus) googleStatus.textContent = status.google_api || 'NOT_CONFIGURED';
        if (openRouterStatus) openRouterStatus.textContent = status.openrouter_api || 'NOT_CONFIGURED';
        if (telegramStatus) telegramStatus.textContent = status.telegram_status || 'OFF';

        openModal('settings-modal');
    } catch (error) {
        console.error("Error opening settings:", error);
        appendMessage('System', `Failed to load settings: ${error.toString()}`, 'sys');
    }
}

function closeSettings() {
    closeModal('settings-modal');
}

function switchSettingsTab(tabName) {
    const tabs = ['api', 'paths', 'demons'];
    if (!tabs.includes(tabName)) return;
    tabs.forEach(name => {
        document.getElementById(`settings-panel-${name}`)?.classList.add('hidden');
        const button = document.getElementById(`tab-${name}`);
        if (button) {
            button.className = "text-on-surface-variant font-label-mono text-label-mono hover:text-primary cursor-pointer";
        }
    });
    document.getElementById(`settings-panel-${tabName}`)?.classList.remove('hidden');
    const activeButton = document.getElementById(`tab-${tabName}`);
    if (activeButton) {
        activeButton.className = "text-primary font-label-mono text-label-mono border-b border-primary pb-0.5 cursor-pointer";
    }

    if ((tabName === 'paths' || tabName === 'demons') && window.orangeBridge?.isAvailable()) {
        window.orangeBridge.json('api_get_system_status').then(status => {
            const vaultEl = document.getElementById('status-vault-path');
            const portEl = document.getElementById('status-orange-port');
            const mcpEl = document.getElementById('status-mcp');
            const watchdogEl = document.getElementById('status-watchdog');
            if (vaultEl) {
                vaultEl.textContent = `${status.obsidian_vault_path || '—'} [${status.vault_status || 'NOT_CONFIGURED'}]`;
            }
            if (portEl) portEl.textContent = status.http_base_url || `:${status.orange_port || '—'}`;
            if (mcpEl) mcpEl.textContent = status.mcp_status || 'NOT_CONFIGURED';
            if (watchdogEl) watchdogEl.textContent = status.watchdog_status || 'NOT_CONFIGURED';
        }).catch(error => console.error('System status error:', error));
    }
}

window.switchSettingsTab = switchSettingsTab;

async function openMCPDashboard() {
    if (window.orangeBridge?.isAvailable()) {
        try {
            const status = await window.orangeBridge.json('api_get_mcp_status');
            const sqliteEl = document.querySelector('#mcp-dashboard-modal [data-mcp="sqlite-status"]');
            const mcpEl = document.querySelector('#mcp-dashboard-modal [data-mcp="mcp-status"]');
            if (sqliteEl) {
                sqliteEl.textContent = status.sqlite
                    ? `${status.sqlite.status} (${status.sqlite.size_mb} MB)`
                    : 'ERROR';
            }
            if (mcpEl) mcpEl.textContent = status.mcp?.status || 'NOT_CONFIGURED';
        } catch (error) {
            console.error('MCP status error:', error);
        }
    }
    openModal('mcp-dashboard-modal');
}

window.openMCPDashboard = openMCPDashboard;

async function saveSettings() {
    if (!window.orangeBridge?.isAvailable()) return;
    try {
        const languageToggle = document.getElementById('language-toggle');
        const settings = {
            telemetry_stream: currentTelemetrySetting,
            telegram_daemon: currentTelegramDaemonSetting,
            auto_backup_enabled: currentAutoBackupSetting,
            auto_push_enabled: currentAutoPushSetting,
            language: languageToggle ? languageToggle.value : 'ru',
        };
        const result = await window.orangeBridge.json('api_save_settings', settings);
        if (result.status === 'success') {
            closeSettings();
            appendMessage('System', 'Settings saved successfully.', 'sys');
        } else {
            appendMessage('System', `Error saving settings: ${result.message}`, 'sys');
        }
    } catch (error) {
        console.error("Error saving settings:", error);
        appendMessage('System', `Failed to save settings: ${error.toString()}`, 'sys');
    }
}

function updateSegmentedSetting(prefix, state) {
    const normalized = state === 'ON' ? 'ON' : 'OFF';
    const buttonOn = document.getElementById(`btn-${prefix}-on`);
    const buttonOff = document.getElementById(`btn-${prefix}-off`);
    if (!buttonOn || !buttonOff) return normalized;
    buttonOn.className = normalized === 'ON'
        ? "px-3 py-1 bg-primary text-on-primary text-[10px] font-bold"
        : "px-3 py-1 text-on-surface text-[10px]";
    buttonOff.className = normalized === 'OFF'
        ? "px-3 py-1 bg-primary text-on-primary text-[10px] font-bold"
        : "px-3 py-1 text-on-surface text-[10px]";
    return normalized;
}

function updateTelemetrySettingsUI(state) {
    currentTelemetrySetting = updateSegmentedSetting('telemetry', state);
}

function updateTelegramDaemonUI(state) {
    currentTelegramDaemonSetting = updateSegmentedSetting('tgdaemon', state);
}

function updateAutoBackupUI(state) {
    currentAutoBackupSetting = updateSegmentedSetting('autobackup', state);
}

function updateAutoPushUI(state) {
    currentAutoPushSetting = updateSegmentedSetting('autopush', state);
}

async function runManualBackup() {
    if (!window.orangeBridge?.isAvailable()) return;
    appendMessage('System', 'Starting local vault backup...', 'sys');
    try {
        const result = await window.orangeBridge.json('api_run_git_backup');
        appendMessage('System', `${result.status}: ${result.message}`, 'sys');
    } catch (error) {
        appendMessage('System', `Backup failed: ${error.toString()}`, 'sys');
    }
}
