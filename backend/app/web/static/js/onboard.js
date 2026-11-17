(() => {
  const form = document.getElementById("signup-form");
  if (!form) return;

  const steps = [...document.querySelectorAll("#steps li")];
  const panels = [...document.querySelectorAll(".step-panel")];
  const video = document.getElementById("camera");
  const canvas = document.getElementById("capture");
  const overlay = document.getElementById("scan-overlay");
  const startBtn = document.getElementById("start-scan");
  const cancelBtn = document.getElementById("cancel-scan");
  const signupError = document.getElementById("signup-error");
  const scanError = document.getElementById("scan-error");
  const doneCopy = document.getElementById("done-copy");

  let userId = null;
  let stream = null;

  function showStep(n) {
    steps.forEach((li) => li.classList.toggle("active", Number(li.dataset.step) === n));
    panels.forEach((p) => {
      p.hidden = Number(p.dataset.panel) !== n;
    });
  }

  function showError(el, msg) {
    el.hidden = !msg;
    el.textContent = msg || "";
  }

  async function openCamera() {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
  }

  function stopCamera() {
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      stream = null;
    }
  }

  function grabFrameBlob() {
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.translate(w, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, w, h);
    return new Promise((resolve) => canvas.toBlob((b) => resolve(b), "image/jpeg", 0.92));
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError(signupError, "");
    const data = Object.fromEntries(new FormData(form).entries());
    const res = await fetch("/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: data.name,
        email: data.email,
        is_rewards_member: true,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showError(signupError, err.detail || "Could not create account");
      return;
    }
    const user = await res.json();
    userId = user.id;
    await fetch(`/auth/customer/session/${userId}`, { method: "POST" });
    showStep(2);
    try {
      await openCamera();
      overlay.textContent = "Camera ready — start face scan";
    } catch (err) {
      showError(scanError, "Camera permission is required for Rewards face enrollment.");
    }
  });

  startBtn.addEventListener("click", async () => {
    if (!userId) return;
    showError(scanError, "");
    startBtn.disabled = true;
    overlay.classList.add("busy");
    const frames = [];
    try {
      for (let i = 0; i < 12; i += 1) {
        overlay.textContent = `Scanning… ${i + 1}/12`;
        const blob = await grabFrameBlob();
        if (blob) frames.push(blob);
        await new Promise((r) => setTimeout(r, 180));
      }
      const body = new FormData();
      frames.forEach((blob, idx) => body.append("frames", blob, `frame_${idx}.jpg`));
      overlay.textContent = "Uploading & enrolling…";
      const res = await fetch(`/users/${userId}/enroll-face-frames`, {
        method: "POST",
        body,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(typeof err.detail === "string" ? err.detail : "Enrollment failed");
      }
      const result = await res.json();
      await fetch(`/auth/customer/session/${userId}`, { method: "POST" });
      stopCamera();
      doneCopy.textContent =
        `Welcome to WatcherMart Rewards (#${result.user_id}). ` +
        `Face enrolled from ${result.samples_captured} frames. ` +
        "You can view aisle interest on your account anytime.";
      showStep(3);
    } catch (err) {
      showError(scanError, err.message || String(err));
      overlay.textContent = "Try again facing the camera";
    } finally {
      startBtn.disabled = false;
      overlay.classList.remove("busy");
    }
  });

  cancelBtn.addEventListener("click", () => {
    stopCamera();
    showStep(1);
  });

  window.addEventListener("beforeunload", stopCamera);
})();
