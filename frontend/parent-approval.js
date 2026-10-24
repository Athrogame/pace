const token = location.hash.slice(1);
history.replaceState(null, "", location.pathname);
const button = document.getElementById("approve");
const result = document.getElementById("result");
if (!token) {
  button.disabled = true;
  result.textContent = "This approval link is missing its code. Open the link in the email again.";
}
button?.addEventListener("click", async () => {
  button.disabled = true;
  try {
    const response = await fetch("/age/parent-decision", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "The link could not be used.");
    result.textContent = data.message;
  } catch (error) {
    result.textContent = error.message;
    button.disabled = false;
  }
});
