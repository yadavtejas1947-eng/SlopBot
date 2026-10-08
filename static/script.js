async function sendMessage() {
    const input = document.getElementById("message");
    const chat = document.getElementById("chat");
    const sendButton = document.getElementById("send");

    const message = input.value.trim();

    if (!message) {
        return;
    }

    // Show user's message
    const userMessage = document.createElement("div");
    userMessage.className = "message user";
    userMessage.textContent = message;

    chat.appendChild(userMessage);

    input.value = "";
    sendButton.disabled = true;

    try {
        const response = await fetch("/chat", {
            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                message: message
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Request failed");
        }

        // Show AI response
        const botMessage = document.createElement("div");
        botMessage.className = "message bot";
        botMessage.textContent = data.reply;

        chat.appendChild(botMessage);

    } catch (error) {
        console.error(error);

        const errorMessage = document.createElement("div");
        errorMessage.className = "message bot";
        errorMessage.textContent =
            "Sorry, something went wrong.";

        chat.appendChild(errorMessage);
    }

    sendButton.disabled = false;

    chat.scrollTop = chat.scrollHeight;
    input.focus();
}


// Send message when Enter is pressed
document.addEventListener("DOMContentLoaded", () => {

    const input = document.getElementById("message");
    const sendButton = document.getElementById("send");

    sendButton.addEventListener("click", sendMessage);

    input.addEventListener("keydown", (event) => {

        if (event.key === "Enter") {
            sendMessage();
        }

    });

});