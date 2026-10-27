// Service Worker — Geolocalisation en arrière-plan

// ✅ Pas de "const API" ici — utiliser une variable locale préfixée
const SW_API_URL = "http://localhost:8026";

self._token = null;

self.addEventListener("message", (event) => {
  if (event.data?.type === "SET_TOKEN") {
    self._token = event.data.token;
  }
  // Recevoir les coordonnées GPS depuis la page
  if (event.data?.type === "SEND_POSITION") {
    const { latitude, longitude, token } = event.data;
    if (token) self._token = token;
    envoyerPosition(latitude, longitude);
  }
});

// Periodic sync (Chrome Android)
self.addEventListener("periodicsync", (event) => {
  if (event.tag === "geo-sync") {
    event.waitUntil(envoyerPositionBackground());
  }
});

async function envoyerPosition(latitude, longitude) {
  if (!self._token) return;
  try {
    await fetch(`${SW_API_URL}/client/localisation`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${self._token}`,
      },
      body: JSON.stringify({ latitude, longitude, source: "gps" }),
    });
  } catch (e) {
    console.warn("[SW-GEO] Envoi position échoué :", e);
  }
}

async function envoyerPositionBackground() {
  // Le SW ne peut pas accéder au GPS directement
  // Les coords sont envoyées via postMessage depuis la page
}