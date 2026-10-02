const customer = JSON.parse(sessionStorage.getItem("mockbank_customer") || "null");

if (!customer) {
    window.location.href = "/";
}

const greetingEl = document.getElementById("greeting");
if (greetingEl && customer) {
    greetingEl.textContent = `Hi, ${customer.first_name} ${customer.last_name}`;
}

const logoutBtn = document.getElementById("logout-btn");
if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
        sessionStorage.removeItem("mockbank_customer");
        window.location.href = "/";
    });
}

function renderCustomerDetails(details, upi) {
    const heading = document.getElementById("customer-section-heading");
    if (heading) heading.textContent = details.login_id;

    const container = document.getElementById("customer-details");
    if (!container) return;
    const rows = [
        ["First Name", details.first_name],
        ["Last Name", details.last_name],
    ];

    container.innerHTML = rows
        .map(([label, value]) => `
            <div class="item">
                <span class="label">${label}</span>
                <span class="value">${value}</span>
            </div>
        `)
        .join("");

    if (upi) {
        const upiItem = document.createElement("div");
        upiItem.className = "item";
        upiItem.innerHTML = `
            <span class="label">UPI ID</span>
            <span class="value"><a href="/edit-upi">${upi.upi_id}</a></span>
        `;
        container.appendChild(upiItem);
    }
}

async function loadCustomerDetails() {
    let details = null;
    let upi = null;

    try {
        const response = await fetch(`/customers/${encodeURIComponent(customer.customer_id)}`);
        if (response.ok) {
            details = await response.json();
        }
    } catch (err) {
        // leave the section blank if unreachable
    }

    try {
        const upiResponse = await fetch(`/upi?customer_id=${encodeURIComponent(customer.customer_id)}`);
        if (upiResponse.ok) {
            upi = await upiResponse.json();
        }
    } catch (err) {
        // no UPI ID yet or unreachable
    }

    if (details) {
        renderCustomerDetails(details, upi);
    }
}

if (customer) {
    loadCustomerDetails();
}
