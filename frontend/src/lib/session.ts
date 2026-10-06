/** A per-tab session id (what the shared host keys runs by); kept in sessionStorage, generated once. */
export function sessionId(): string {
  const key = 'matter_sid';
  try {
    let sid = sessionStorage.getItem(key);
    if (!sid) {
      const bytes = new Uint8Array(9);
      crypto.getRandomValues(bytes);
      sid = 'tab-' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
      sessionStorage.setItem(key, sid);
    }
    return sid;
  } catch {
    return 'tab-' + Math.random().toString(16).slice(2, 14);
  }
}
