const DATABASE = 'vista-runs';
const VERSION = 1;

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains('runs')) db.createObjectStore('runs', { keyPath: 'id' });
      if (!db.objectStoreNames.contains('videos')) db.createObjectStore('videos');
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function saveRun(run, video) {
  const db = await openDatabase();
  try {
    await new Promise((resolve, reject) => {
      const transaction = db.transaction(['runs', 'videos'], 'readwrite');
      transaction.objectStore('runs').put(run);
      transaction.objectStore('videos').put(video, run.id);
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally {
    db.close();
  }
}

export async function listRuns() {
  const db = await openDatabase();
  try {
    const rows = await requestResult(db.transaction('runs').objectStore('runs').getAll());
    return rows.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  } finally {
    db.close();
  }
}

export async function getRun(id) {
  const db = await openDatabase();
  try {
    const transaction = db.transaction(['runs', 'videos']);
    const [run, video] = await Promise.all([
      requestResult(transaction.objectStore('runs').get(id)),
      requestResult(transaction.objectStore('videos').get(id)),
    ]);
    return run && video ? { run, video } : null;
  } finally {
    db.close();
  }
}

export async function deleteRun(id) {
  const db = await openDatabase();
  try {
    await new Promise((resolve, reject) => {
      const transaction = db.transaction(['runs', 'videos'], 'readwrite');
      transaction.objectStore('runs').delete(id);
      transaction.objectStore('videos').delete(id);
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
    });
  } finally {
    db.close();
  }
}
