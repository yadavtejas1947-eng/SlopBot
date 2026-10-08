const chat = document.getElementById("chat");
const input = document.getElementById("message");
const sendButton = document.getElementById("send");

const csrfToken = window.CSRF_TOKEN;


function scrollToBottom() {

    chat.scrollTop = chat.scrollHeight;

}


function createMessage(
    text,
    type
) {

    const message = document.createElement("div");

    message.className =
        `message ${type}`;

    message.textContent = text;

    return message;

}


function addMessage(
    text,
    type
) {

    const message =
        createMessage(text, type);

    chat.appendChild(message);

    scrollToBottom();

    return message;

}


function removeWelcome() {

    const welcome =
        document.querySelector(".welcome");

    if (welcome) {
        welcome.remove();
    }

}


function setLoading(
    loading
) {

    sendButton.disabled = loading;
    input.disabled = loading;

}


async function loadHistory() {

    try {

        const response =
            await fetch("/history");

        if (!response.ok) {
            return;
        }

        const history =
            await response.json();

        if (!history.length) {
            return;
        }

        removeWelcome();

        for (const chatItem of history) {

            addMessage(
                chatItem.message,
                "user"
            );

            addMessage(
                chatItem.response,
                "bot"
            );

        }

    } catch (error) {

        console.error(
            "History error:",
            error
        );

    }

}


async function sendMessage() {

    const message =
        input.value.trim();

    if (!message) {
        return;
    }

    if (message.length > 10000) {

        addMessage(
            "Your message is too long.",
            "bot"
        );

        return;
    }

    removeWelcome();

    addMessage(
        message,
        "user"
    );

    input.value = "";

    input.style.height = "auto";

    setLoading(true);


    // Temporary loading message
    const loadingMessage =
        addMessage(
            "Thinking...",
            "bot"
        );


    try {

        const response =
            await fetch(
                "/chat",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json",

                        "X-CSRF-Token":
                            csrfToken
                    },

                    body: JSON.stringify({
                        message: message
                    })
                }
            );


        const data =
            await response.json();


        loadingMessage.remove();


        if (!response.ok) {

            throw new Error(
                data.error ||
                "Request failed."
            );

        }


        addMessage(
            data.reply,
            "bot"
        );


    } catch (error) {

        console.error(
            "Chat error:",
            error
        );

        addMessage(
            error.message ||
            "Something went wrong. Please try again.",
            "bot"
        );

    } finally {

        setLoading(false);

        input.focus();

    }

}


sendButton.addEventListener(
    "click",
    sendMessage
);


input.addEventListener(
    "keydown",
    function(event) {

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {

            event.preventDefault();

            if (!sendButton.disabled) {
                sendMessage();
            }

        }

    }
);


input.addEventListener(
    "input",
    function() {

        this.style.height = "auto";

        this.style.height =
            Math.min(
                this.scrollHeight,
                160
            ) + "px";

    }
);


document.addEventListener(
    "DOMContentLoaded",
    function() {

        loadHistory();

        input.focus();

    }
);