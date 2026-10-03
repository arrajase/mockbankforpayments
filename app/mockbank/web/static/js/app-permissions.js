const messageBox = document.getElementById("message");
const list = document.getElementById("request-list");

const PURPOSE_LABELS = {
    LINK: "confirm this UPI ID is yours",
    BALANCE: "see your balance",
    STATEMENT: "read your statement",
};

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

function describePurposes(consent) {
    return consent.purposes
        .map((p) => (p === "STATEMENT" ? `${PURPOSE_LABELS[p]} (${consent.statement_from} to ${consent.statement_to})` : PURPOSE_LABELS[p] || p))
        .join(", ");
}

function actionsFor(consent) {
    if (consent.status === "PENDING") {
        return `
            <form class="request-actions">
                <input type="password" name="upi_pin" inputmode="numeric" pattern="[0-9]{4,6}" maxlength="6" placeholder="UPI PIN" autocomplete="off" required>
                <button type="submit" class="btn-primary">ALLOW</button>
                <button type="button" class="btn-secondary" data-action="reject">DENY</button>
            </form>`;
    }
    if (consent.status === "ACTIVE") {
        return `<div class="request-actions"><button type="button" class="btn-secondary" data-action="revoke">REVOKE</button></div>`;
    }
    return "";
}

function renderConsents(consents) {
    if (consents.length === 0) {
        list.innerHTML = `<p class="empty-state">No apps have asked for access.</p>`;
        return;
    }

    list.innerHTML = consents
        .map(
            (c) => `
            <div class="request-card" data-id="${escapeHtml(c.consent_id)}">
                <div class="request-title">${escapeHtml(c.client_name || "An app")} <span class="request-status">${escapeHtml(c.status)}</span></div>
                <div class="request-meta">Wants to ${escapeHtml(describePurposes(c))}</div>
                <div class="request-meta">UPI ID ${escapeHtml(c.upi_id)} · until ${escapeHtml(new Date(c.expires_at).toLocaleString())}</div>
                ${actionsFor(c)}
            </div>
        `
        )
        .join("");

    list.querySelectorAll(".request-card").forEach((card) => {
        const id = card.dataset.id;
        const form = card.querySelector("form");
        if (form) {
            form.addEventListener("submit", async (event) => {
                event.preventDefault();
                await act(id, "approve", { upi_pin: form.upi_pin.value });
            });
        }
        card.querySelectorAll("button[data-action]").forEach((btn) => {
            btn.addEventListener("click", () => act(id, btn.dataset.action));
        });
    });
}

async function act(consentId, action, body) {
    messageBox.className = "message";
    try {
        const { ok, data } = await api(`/me/consents/${encodeURIComponent(consentId)}/${action}`, { method: "POST", body: body || {} });
        if (!ok) {
            showMessage(errorMessage(data, "Could not update the permission"), "error");
            return;
        }
        showMessage(`Permission ${data.status.toLowerCase()}.`, "success");
        loadConsents();
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
}

async function loadConsents() {
    try {
        const { ok, data } = await api("/me/consents");
        if (!ok) {
            showMessage(errorMessage(data, "Could not load permissions."), "error");
            return;
        }
        renderConsents(data);
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
}

if (customer) {
    loadConsents();
}
