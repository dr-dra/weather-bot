document.addEventListener("DOMContentLoaded", function () {
  const chatBox = document.getElementById("chat-box");
  const welcomeMessage =
    "Hello! I am Travel Bloggers Low budget WeatherBot. How can I assist you today?";
  chatBox.innerHTML += `<div class="message bot"><p>${welcomeMessage}</p></div>`;
});

function sendMessage() {
  const userInput = document.getElementById("user-input").value;
  const chatBox = document.getElementById("chat-box");
  if (userInput.trim() === "") return;

  chatBox.innerHTML += `<div class="message user"><p>${userInput}</p></div>`;
  document.getElementById("user-input").value = "";

  fetch("/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message: userInput }),
  })
    .then((response) => response.json())
    .then((data) => {
      chatBox.innerHTML += `<div class="message bot"><p>${data.response}</p></div>`;
      chatBox.scrollTop = chatBox.scrollHeight;
    });
}

document
  .getElementById("user-input")
  .addEventListener("keypress", function (e) {
    if (e.key === "Enter") {
      sendMessage();
    }
  });
