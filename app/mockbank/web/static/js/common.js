// Authentication is the HttpOnly session cookie; sessionStorage only holds the name shown in the navbar.
const customer = JSON.parse(sessionStorage.getItem("mockbank_customer") || "null");

if (!customer) {
    window.location.href = "/";
}

function errorMessage(data, fallback) {
    if (data && data.error && data.error.message) return data.error.message;
    return fallback;
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// fetch wrapper for the bank's own API: JSON in/out, and back to the login page when the session has expired.
async function api(path, options = {}) {
    const init = { ...options, headers: { ...(options.headers || {}) } };
    if (init.body !== undefined && typeof init.body !== "string") {
        init.body = JSON.stringify(init.body);
        init.headers["Content-Type"] = "application/json";
    }
    const response = await fetch(path, init);
    if (response.status === 401) {
        sessionStorage.removeItem("mockbank_customer");
        window.location.href = "/";
        throw new Error("session expired");
    }
    const data = response.status === 204 ? null : await response.json().catch(() => null);
    return { ok: response.ok, status: response.status, data };
}

const greetingEl = document.getElementById("greeting");
if (greetingEl && customer) {
    greetingEl.textContent = `Hi, ${customer.first_name} ${customer.last_name}`;
}

const logoutBtn = document.getElementById("logout-btn");
if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
        try {
            await fetch("/auth/logout", { method: "POST" });
        } finally {
            sessionStorage.removeItem("mockbank_customer");
            window.location.href = "/";
        }
    });
}

// Links every signed-in page shares.
const sidebarNav = document.querySelector(".sidebar nav");
if (sidebarNav) {
    [["/pending-requests", "Pending Requests"], ["/app-permissions", "App Permissions"]].forEach(([href, label]) => {
        if (!sidebarNav.querySelector(`a[href="${href}"]`)) {
            const link = document.createElement("a");
            link.href = href;
            link.textContent = label;
            sidebarNav.appendChild(link);
        }
    });
}

function renderCustomerDetails(details, upis) {
    const heading = document.getElementById("customer-section-heading");
    if (heading) heading.textContent = details.login_id;

    const container = document.getElementById("customer-details");
    if (!container) return;
    const rows = [
        ["First Name", escapeHtml(details.first_name)],
        ["Last Name", escapeHtml(details.last_name)],
    ];
    upis.forEach((upi) => {
        rows.push(["UPI ID", `<a href="/edit-upi?upi=${encodeURIComponent(upi.upi_id)}">${escapeHtml(upi.upi_id)}</a>`]);
    });

    container.innerHTML = rows
        .map(([label, value]) => `
            <div class="item">
                <span class="label">${label}</span>
                <span class="value">${value}</span>
            </div>
        `)
        .join("");
}

async function loadCustomerDetails() {
    try {
        const [me, upis] = await Promise.all([api("/me"), api("/upi")]);
        if (me.ok) {
            renderCustomerDetails(me.data, upis.ok ? upis.data : []);
        }
    } catch (err) {
        // leave the section blank if unreachable
    }
}

if (customer) {
    loadCustomerDetails();
}
