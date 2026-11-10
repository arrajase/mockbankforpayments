const messageBox = document.getElementById("message");
const form = document.getElementById("edit-upi-form");
const pinForm = document.getElementById("pin-form");
const accountSelect = document.getElementById("account_id");

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

let currentUpi = null;
let mobileNumber = null;

const mobileLinkBtn = document.getElementById("mobile-link-btn");

function renderMobileLink() {
    const note = document.getElementById("mobile-link-note");
    if (!mobileNumber) {
        note.innerHTML = `Add a mobile number on <a href="/profile#mobile-section">your profile</a> to link it to this UPI ID.`;
        mobileLinkBtn.hidden = true;
        return;
    }
    note.textContent = currentUpi.mobile_linked
        ? `Linked to ${mobileNumber}. Apps that look up this number find this UPI ID.`
        : `Not linked. Link ${mobileNumber} so apps can find this UPI ID by your mobile number. Any other UPI ID linked to it is unlinked.`;
    mobileLinkBtn.textContent = currentUpi.mobile_linked ? "UNLINK MOBILE NUMBER" : "LINK MOBILE NUMBER";
    mobileLinkBtn.hidden = false;
}

async function init() {
    try {
        const { ok, data: upis } = await api("/upi");
        if (!ok) {
            showMessage("Unable to load UPI IDs.", "error");
            return;
        }
        const wanted = new URLSearchParams(window.location.search).get("upi");
        currentUpi = upis.find((u) => u.upi_id === wanted) || upis[0];
        if (!currentUpi) {
            window.location.href = "/create-upi";
            return;
        }
        document.getElementById("upi-id-label").textContent = currentUpi.upi_id;
        document.getElementById("pin-heading").textContent = currentUpi.pin_set ? "Change UPI PIN" : "Set UPI PIN";
        document.getElementById("current-pin-field").hidden = !currentUpi.pin_set;
        if (!currentUpi.pin_set) {
            showMessage("This UPI ID has no UPI PIN yet. Set one to approve requests from apps.", "error");
        }

        const me = await api("/me");
        if (me.ok) {
            mobileNumber = me.data.mobile_number;
            renderMobileLink();
        }
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
        return;
    }

    try {
        const { ok, data: accounts } = await api("/accounts");
        if (!ok) {
            showMessage("Could not load your accounts.", "error");
            return;
        }

        accountSelect.innerHTML = accounts
            .map(
                (a) =>
                    `<option value="${escapeHtml(a.account_id)}" ${a.account_id === currentUpi.account_id ? "selected" : ""}>${escapeHtml(a.account_name)} (${escapeHtml(a.account_number)}, ${escapeHtml(a.currency)})</option>`
            )
            .join("");
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.className = "message";

    try {
        const { ok, data } = await api(`/upi/${encodeURIComponent(currentUpi.upi_id)}`, {
            method: "PUT",
            body: { account_id: accountSelect.value },
        });
        if (!ok) {
            showMessage(errorMessage(data, "Could not update linked account"), "error");
            return;
        }

        showMessage("Linked account updated successfully", "success");
        setTimeout(() => {
            window.location.href = "/profile";
        }, 1200);
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
});

mobileLinkBtn.addEventListener("click", async () => {
    messageBox.className = "message";
    const linked = !currentUpi.mobile_linked;
    mobileLinkBtn.disabled = true;
    try {
        const { ok, data } = await api(`/upi/${encodeURIComponent(currentUpi.upi_id)}/mobile-link`, { method: "PUT", body: { linked } });
        if (!ok) {
            showMessage(errorMessage(data, "Could not change the mobile number link"), "error");
            return;
        }
        currentUpi = data;
        renderMobileLink();
        showMessage(linked ? "Mobile number linked to this UPI ID" : "Mobile number unlinked", "success");
        loadCustomerDetails();
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    } finally {
        mobileLinkBtn.disabled = false;
    }
});

pinForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.className = "message";

    const newPin = document.getElementById("new_pin").value;
    if (newPin !== document.getElementById("confirm_new_pin").value) {
        showMessage("New UPI PIN and Confirm UPI PIN do not match.", "error");
        return;
    }
    const body = { new_pin: newPin };
    if (currentUpi.pin_set) body.current_pin = document.getElementById("current_pin").value;

    try {
        const { ok, data } = await api(`/upi/${encodeURIComponent(currentUpi.upi_id)}/pin`, { method: "PUT", body });
        if (!ok) {
            showMessage(errorMessage(data, "Could not update UPI PIN"), "error");
            return;
        }
        currentUpi = data;
        pinForm.reset();
        document.getElementById("pin-heading").textContent = "Change UPI PIN";
        document.getElementById("current-pin-field").hidden = false;
        showMessage("UPI PIN saved", "success");
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
});

if (customer) {
    init();
}
