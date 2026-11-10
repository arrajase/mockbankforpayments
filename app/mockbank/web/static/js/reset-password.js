const messageBox = document.getElementById("message");
const form = document.getElementById("reset-password-form");

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.className = "message";

    const newPassword = document.getElementById("new_password").value;
    const confirmPassword = document.getElementById("confirm_password").value;
    if (newPassword !== confirmPassword) {
        showMessage("New Password and Confirm New Password do not match.", "error");
        return;
    }

    try {
        const { ok, data } = await api("/me/password", {
            method: "PUT",
            body: { new_password: newPassword, confirm_password: confirmPassword },
        });
        if (!ok) {
            showMessage(errorMessage(data, "Could not reset password"), "error");
            return;
        }
        form.reset();
        showMessage("Password reset successfully", "success");
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
});
