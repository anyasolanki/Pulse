const storageKey = 'pulse-local-user-id';

export function localUserHeaders(): Record<string, string> {
  let id = window.localStorage.getItem(storageKey);
  if (!id) {
    id = window.crypto.randomUUID();
    window.localStorage.setItem(storageKey, id);
  }
  return { 'X-Pulse-Local-User': id };
}
