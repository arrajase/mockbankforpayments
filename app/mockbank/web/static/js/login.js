const form = document.getElementById("login-form");
const messageBox = document.getElementById("message");

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.className = "message";

    const payload = {
        login_id: document.getElementById("login_id").value.trim(),
        password: document.getElementById("password").value,
    };

    try {
        const response = await fetch("/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();

        if (!response.ok) {
            showMessage((data.error && data.error.message) || "Login failed", "error");
            return;
        }

        // The server set the session cookie; keep only the display name here.
        sessionStorage.setItem("mockbank_customer", JSON.stringify({ first_name: data.first_name, last_name: data.last_name }));
        window.location.href = "/profile";
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
});
