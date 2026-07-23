/* Dünner Fetch-Wrapper: JSON rein/raus, Fehler als deutsche Meldung. */

async function request(method, url, body) {
  let resp;
  try {
    resp = await fetch(url, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Keine Verbindung zum Analyse-Dienst.");
  }
  let data = null;
  try { data = await resp.json(); } catch { /* leere Antwort ist ok */ }
  if (!resp.ok) {
    const detail = data && (data.detail || data.message);
    throw new Error(typeof detail === "string" ? detail : `Fehler ${resp.status}`);
  }
  return data;
}

export const api = {
  get: (url) => request("GET", url),
  post: (url, body) => request("POST", url, body ?? {}),
  put: (url, body) => request("PUT", url, body),
};
