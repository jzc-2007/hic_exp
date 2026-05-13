(() => {
  const ready = (fn) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  };

  const insertRecognizedText = (textarea, baseText, transcript) => {
    const addition = transcript.trim();
    const prefix = baseText.trimEnd();
    if (!addition) {
      textarea.value = baseText;
    } else if (!prefix) {
      textarea.value = addition;
    } else {
      textarea.value = `${prefix} ${addition}`;
    }
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  };

  const setupVoiceInput = () => {
    const form = document.querySelector("[data-chat-form]");
    if (!form) return;
    const textarea = form.querySelector("[data-mention-input]");
    if (!textarea || textarea.dataset.voiceReady === "1") return;
    textarea.dataset.voiceReady = "1";

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const tools = document.createElement("div");
    tools.className = "composer-tools";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "voice-button";
    button.textContent = "Voice";
    button.title = "Dictate into this message";
    const status = document.createElement("span");
    status.className = "muted voice-status";
    status.setAttribute("aria-live", "polite");
    tools.append(button, status);

    const label = textarea.closest("label");
    if (label) label.appendChild(tools);

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "zh-CN";

    let listening = false;
    let baseText = "";
    let finalText = "";

    const setListening = (value) => {
      listening = value;
      button.classList.toggle("active", listening);
      button.textContent = listening ? "Stop" : "Voice";
      status.textContent = listening ? "listening..." : "";
    };

    recognition.onstart = () => {
      baseText = textarea.value;
      finalText = "";
      setListening(true);
    };

    recognition.onresult = (event) => {
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const text = result[0] ? result[0].transcript : "";
        if (result.isFinal) finalText += text;
        else interim += text;
      }
      insertRecognizedText(textarea, baseText, `${finalText} ${interim}`);
    };

    recognition.onerror = (event) => {
      const error = event.error ? String(event.error).replace(/-/g, " ") : "voice error";
      status.textContent = error;
    };

    recognition.onend = () => {
      setListening(false);
    };

    button.addEventListener("click", () => {
      if (listening) {
        recognition.stop();
        return;
      }
      try {
        recognition.start();
      } catch (error) {
        status.textContent = "voice unavailable";
      }
    });
  };

  ready(setupVoiceInput);
})();
