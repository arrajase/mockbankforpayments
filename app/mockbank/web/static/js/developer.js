const messageBox = document.getElementById("message");
const list = document.getElementById("client-list");
const newKeyCard = document.getElementById("new-key");

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

// Shows a freshly issued key (and webhook secret) once.
function showNewSecrets(apiKey, webhookSecret) {
    document.getElementById("new-api-key").textContent = apiKey || "";
    document.getElementById("new-webhook-secret").textContent = webhookSecret || "";
    document.getElementById("new-secret-row").hidden = !webhookSecret;
    newKeyCard.querySelector(".secret-row").hidden = !apiKey;
    newKeyCard.hidden = false;
    newKeyCard.scrollIntoView({ behavior: "smooth", block: "center" });
}

document.getElementById("dismiss-new-key").addEventListener("click", () => {
    newKeyCard.hidden = true;
    document.getElementById("new-api-key").textContent = "";
    document.getElementById("new-webhook-secret").textContent = "";
});

newKeyCard.querySelectorAll(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
        const value = document.getElementById(btn.dataset.copy).textContent;
        try {
            await navigator.clipboard.writeText(value);
            btn.textContent = "COPIED";
            setTimeout(() => (btn.textContent = "COPY"), 1500);
        } catch (err) {
            showMessage("Couldn't copy; select the text and copy it instead.", "error");
        }
    });
});

function renderClients(clients) {
    if (clients.length === 0) {
        list.innerHTML = `<p class="empty-state">No apps yet.</p>`;
        return;
    }

    list.innerHTML = clients
        .map(
            (c) => `
            <div class="request-card" data-id="${escapeHtml(c.client_id)}">
                <div class="request-title">${escapeHtml(c.name)} <span class="request-status">${c.active ? "ACTIVE" : "INACTIVE"}</span></div>
                <div class="request-meta">Key <code>${escapeHtml(c.key_hint)}</code> · created ${escapeHtml(new Date(c.created_at).toLocaleDateString())}</div>
                <div class="request-meta">Client ID <code>${escapeHtml(c.client_id)}</code></div>
                <form class="request-actions webhook-form">
                    <input type="url" name="webhook_url" value="${escapeHtml(c.webhook_url || "")}" placeholder="Webhook URL (none)" class="webhook-input">
                    <button type="submit" class="btn-secondary">SAVE WEBHOOK</button>
                </form>
                <div class="request-actions">
                    <button type="button" class="btn-secondary" data-action="reveal-secret">SHOW WEBHOOK SECRET</button>
                    <button type="button" class="btn-secondary" data-action="rotate-secret">NEW WEBHOOK SECRET</button>
                    <button type="button" class="btn-secondary" data-action="rotate-key">NEW API KEY</button>
                    <button type="button" class="btn-secondary" data-action="toggle-active">${c.active ? "DEACTIVATE" : "REACTIVATE"}</button>
                </div>
                <div class="request-meta secret-output" hidden></div>
            </div>
        `
        )
        .join("");

    list.querySelectorAll(".request-card").forEach((card) => {
        const id = card.dataset.id;
        const client = clients.find((c) => c.client_id === id);

        card.querySelector(".webhook-form").addEventListener("submit", async (event) => {
            event.preventDefault();
            const url = event.target.webhook_url.value.trim();
            await call(`/me/api-clients/${encodeURIComponent(id)}`, "PUT", { webhook_url: url || null }, "Webhook URL saved.");
        });

        card.querySelectorAll("button[data-action]").forEach((btn) => {
            btn.addEventListener("click", () => act(card, client, btn.dataset.action));
        });
    });
}

async function call(path, method, body, successText) {
    messageBox.className = "message";
    try {
        const { ok, data } = await api(path, { method, body });
        if (!ok) {
            showMessage(errorMessage(data, "Something went wrong"), "error");
            return null;
        }
        if (successText) showMessage(successText, "success");
        loadClients();
        return data;
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
        return null;
    }
}

async function act(card, client, action) {
    const base = `/me/api-clients/${encodeURIComponent(client.client_id)}`;

    if (action === "reveal-secret") {
        const { ok, data } = await api(`${base}/webhook-secret`);
        const out = card.querySelector(".secret-output");
        if (ok) {
            out.innerHTML = `Webhook secret <code>${escapeHtml(data.webhook_secret)}</code>`;
            out.hidden = false;
        } else {
            showMessage(errorMessage(data, "Could not load the webhook secret"), "error");
        }
        return;
    }

    if (action === "rotate-key") {
        if (!confirm(`Issue a new API key for ${client.name}? The current key stops working immediately.`)) return;
        const data = await call(`${base}/rotate-key`, "POST", {}, "New API key issued. The old key no longer works.");
        if (data) showNewSecrets(data.api_key, null);
        return;
    }

    if (action === "rotate-secret") {
        if (!confirm(`Issue a new webhook secret for ${client.name}? Webhooks will be signed with the new secret from now on.`)) return;
        const data = await call(`${base}/rotate-webhook-secret`, "POST", {}, "New webhook secret issued.");
        if (data) showNewSecrets(null, data.webhook_secret);
        return;
    }

    if (action === "toggle-active") {
        if (client.active && !confirm(`Deactivate ${client.name}? Its API key will be rejected until you reactivate it.`)) return;
        await call(base, "PUT", { active: !client.active }, client.active ? "App deactivated." : "App reactivated.");
    }
}

document.getElementById("create-client-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("client-name").value.trim();
    const webhook = document.getElementById("client-webhook").value.trim();
    const data = await call("/me/api-clients", "POST", { name, webhook_url: webhook || null }, `App ${name} registered.`);
    if (data) {
        event.target.reset();
        showNewSecrets(data.api_key, data.webhook_secret);
    }
});

async function loadClients() {
    try {
        const { ok, data } = await api("/me/api-clients");
        if (!ok) {
            showMessage(errorMessage(data, "Could not load your apps."), "error");
            return;
        }
        renderClients(data);
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
}

if (customer) {
    loadClients();
}
