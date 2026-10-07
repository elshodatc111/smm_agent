/** Qoralama fayllari brauzerda (IndexedDB) saqlanadi: sahifa yopilsa ham tanlangan rasm/video yo'qolmaydi. */
const DB = 'smm-drafts', ST = 'files'
const open = () => new Promise<IDBDatabase>((res, rej) => {
  const r = indexedDB.open(DB, 1)
  r.onupgradeneeded = () => r.result.createObjectStore(ST)
  r.onsuccess = () => res(r.result)
  r.onerror = () => rej(r.error)
})
const tx = async <T,>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T | undefined> => {
  try {
    const db = await open()
    return await new Promise<T>((res, rej) => { const q = fn(db.transaction(ST, mode).objectStore(ST)); q.onsuccess = () => res(q.result); q.onerror = () => rej(q.error) })
  } catch { return undefined }
}
export const saveDraftFiles = (key: string, files: File[]) => (files.length ? tx('readwrite', (s) => s.put(files, key)) : tx('readwrite', (s) => s.delete(key)))
export const loadDraftFiles = async (key: string): Promise<File[]> => ((await tx<File[]>('readonly', (s) => s.get(key))) || [])
export const clearDraftFiles = (key: string) => tx('readwrite', (s) => s.delete(key))
