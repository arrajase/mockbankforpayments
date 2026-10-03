if (customer) {
    document.getElementById("first_name").value = customer.first_name;
    document.getElementById("last_name").value = customer.last_name;
}

const form = document.getElementById("create-account-form");
const messageBox = document.getElementById("message");

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.className = "message";

    const accountType = document.querySelector('input[name="account_type"]:checked').value;
    const payload = {
        account_type: accountType,
        account_name: document.getElementById("account_name").value.trim(),
        currency: document.getElementById("currency").value,
    };

    try {
        const { ok, data } = await api("/accounts", { method: "POST", body: payload });
        if (!ok) {
            showMessage(errorMessage(data, "Could not create account"), "error");
            return;
        }

        showMessage("Account creation successful", "success");
        setTimeout(() => {
            window.location.href = "/profile";
        }, 1200);
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
});
