// Popup — 检查 API 状态, 快捷操作
document.addEventListener("DOMContentLoaded", async () => {
  const apiUrlInput = document.getElementById("apiUrl");
  const apiStatus = document.getElementById("apiStatus");

  // 从 storage 恢复 API URL
  const { apiUrl } = await chrome.storage.local.get("apiUrl");
  if (apiUrl) apiUrlInput.value = apiUrl;

  // 检查连接
  async function checkHealth() {
    try {
      const url = apiUrlInput.value || "http://localhost:8800";
      const resp = await fetch(`${url}/api/v1/health`);
      const data = await resp.json();
      apiStatus.innerHTML = "connected";
      apiStatus.style.color = "#22c55e";
    } catch (e) {
      apiStatus.innerHTML = "disconnected";
      apiStatus.style.color = "#ef4444";
    }
  }

  checkHealth();

  // 按钮操作
  document.getElementById("recordBtn").addEventListener("click", async () => {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, { action: "toggleRecord" });
      window.close();
    }
  });

  document.getElementById("injectBtn").addEventListener("click", async () => {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, { action: "injectToPacs" });
      window.close();
    }
  });

  document.getElementById("resetBtn").addEventListener("click", async () => {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, { action: "reset" });
      window.close();
    }
  });

  apiUrlInput.addEventListener("change", async () => {
    await chrome.storage.local.set({ apiUrl: apiUrlInput.value });
    checkHealth();
  });
});
