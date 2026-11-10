const storageKey = 'clarora-auth-change';

let accountSnapshot = null;
let revision = 0;
export const getAccountSnapshot = () => accountSnapshot;
export const getAuthRevision = () => revision;
export function rememberAccount(account, expectedRevision = revision) {
  if (expectedRevision === revision) accountSnapshot = account;
  return accountSnapshot;
}

export function notifyAuthChange(account) {
  revision++;
  accountSnapshot = account ?? null;
  const event = new Event('authchange');
  event.account = accountSnapshot;
  window.dispatchEvent(event);
  // Only a change marker is shared; session credentials remain in HttpOnly cookies.
  try { localStorage.setItem(storageKey, crypto.randomUUID()); } catch {}
}

export function subscribeAuthChange(refresh) {
  const visible = () => { if (document.visibilityState === 'visible') refresh(); };
  const storage = event => { if (event.key === storageKey) { revision++; accountSnapshot = null; refresh(); } };
  window.addEventListener('authchange', refresh);
  window.addEventListener('focus', refresh);
  window.addEventListener('pageshow', refresh);
  window.addEventListener('storage', storage);
  document.addEventListener('visibilitychange', visible);
  return () => {
    window.removeEventListener('authchange', refresh);
    window.removeEventListener('focus', refresh);
    window.removeEventListener('pageshow', refresh);
    window.removeEventListener('storage', storage);
    document.removeEventListener('visibilitychange', visible);
  };
}
