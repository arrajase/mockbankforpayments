const messageBox = document.getElementById("message");
const list = document.getElementById("request-list");

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

function formatAmount(cents, currency) {
    return `${currency} ${(cents / 100).toFixed(2)}`;
}

function renderRequests(requests) {
    if (requests.length === 0) {
        list.innerHTML = `<p class="empty-state">No pending requests.</p>`;
        return;
    }

    list.innerHTML = requests
        .map(
            (r) => `
            <div class="request-card" data-id="${escapeHtml(r.collect_id)}">
                <div class="request-title">${escapeHtml(r.payee_name || r.payee_upi_id)} requests ${escapeHtml(formatAmount(r.amount_cents, r.currency))}</div>
                <div class="request-meta">To ${escapeHtml(r.payee_upi_id)} · from your ${escapeHtml(r.payer_upi_id)}</div>
                ${r.note ? `<div class="request-meta">“${escapeHtml(r.note)}”</div>` : ""}
                <div class="request-meta">Expires ${escapeHtml(new Date(r.expires_at).toLocaleString())}</div>
                <form class="request-actions">
                    <input type="password" name="upi_pin" inputmode="numeric" pattern="[0-9]{4,6}" maxlength="6" placeholder="UPI PIN" autocomplete="off" required>
                    <button type="submit" class="btn-primary">APPROVE</button>
                    <button type="button" class="btn-secondary decline-btn">DECLINE</button>
                </form>
            </div>
        `
        )
        .join("");

    list.querySelectorAll(".request-card").forEach((card) => {
        const id = card.dataset.id;
        const form = card.querySelector("form");
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            await act(id, "approve", { upi_pin: form.upi_pin.value });
        });
        card.querySelector(".decline-btn").addEventListener("click", () => act(id, "decline"));
    });
}

async function act(collectId, action, body) {
    messageBox.className = "message";
    try {
        const { ok, data } = await api(`/me/collect-requests/${encodeURIComponent(collectId)}/${action}`, { method: "POST", body: body || {} });
        if (!ok) {
            showMessage(errorMessage(data, `Could not ${action} the request`), "error");
            if (data && data.error && data.error.code === "COLLECT_EXPIRED") loadRequests();
            return;
        }
        if (data.status === "SUCCESS") {
            showMessage(`Paid ${formatAmount(data.amount_cents, data.currency)} to ${data.payee_upi_id}.`, "success");
        } else if (data.status === "FAILED") {
            showMessage(`Payment failed: ${data.failure_reason === "INSUFFICIENT_FUNDS" ? "insufficient funds" : data.failure_reason}.`, "error");
        } else {
            showMessage(`Request ${data.status.toLowerCase()}.`, "success");
        }
        loadRequests();
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
}

async function loadRequests() {
    try {
        const { ok, data } = await api("/me/collect-requests");
        if (!ok) {
            showMessage(errorMessage(data, "Could not load requests."), "error");
            return;
        }
        renderRequests(data);
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
}

if (customer) {
    loadRequests();
}
