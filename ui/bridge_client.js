(function initializeBridgeClient() {
    function requireApiMethod(name) {
        const api = window.pywebview?.api;
        if (!api || typeof api[name] !== "function") {
            throw new Error(`Bridge method is unavailable: ${name}`);
        }
        return api[name].bind(api);
    }

    window.orangeBridge = {
        isAvailable() {
            return Boolean(window.pywebview?.api);
        },

        async call(name, ...args) {
            return requireApiMethod(name)(...args);
        },

        async json(name, ...args) {
            const raw = await requireApiMethod(name)(...args);
            if (raw && typeof raw === "object") {
                return raw;
            }
            try {
                return JSON.parse(raw);
            } catch (error) {
                throw new Error(`Bridge method returned invalid JSON: ${name}`);
            }
        },
    };
})();
