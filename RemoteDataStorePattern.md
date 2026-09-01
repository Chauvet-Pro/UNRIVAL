# Remote Data Store Pattern

A step-by-step guide for adding a new remote-fetched, version-checked, locally-cached MobX State Tree store to the UNRIVAL app.

## Overview

This pattern lets you:
- Fetch JSON data from a remote URL
- Cache it locally in AsyncStorage (survives app restarts)
- Only update when the remote `version` number is higher than what's cached
- Silently fall back to cached data when offline

**Reference implementation:** `ProductsStore` — see `Store/ProductsStore.ts`

---

## Remote JSON Format

Your remote JSON must include a top-level `version` number:

```json
{
  "version": 1,
  "yourData": [
    { "id": 1, "name": "Item One", "details": { ... } }
  ]
}
```

Bump `version` whenever you update the data. The app only pulls new data when `remote.version > local.version`.

---

## Step 1: Create the Store File

Create `Store/YourNewStore.ts`:

```typescript
import { types, flow } from 'mobx-state-tree';

const DATA_URL = 'https://raw.githubusercontent.com/Chauvet-Pro/UNRIVAL/main/yourData.json';

const YourNewStore = types
  .model('YourNewStore', {
    version: types.optional(types.number, 0),
    yourData: types.optional(types.frozen(), []),
  })
  .views((self) => ({
    // Add lookup views as needed
    getItemById(id: number) {
      return (self.yourData as any[]).find((item: any) => item.id === id);
    },
  }))
  .actions((self) => ({
    fetchData: flow(function* fetchData() {
      try {
        const response = yield fetch(DATA_URL);
        const data = yield response.json();
        if (data.version > self.version) {
          self.version = data.version;
          self.yourData = data.yourData;
        }
      } catch (error) {
        // Silently fall back to cached data
        console.log('YourNewStore: fetch failed, using cached data', error);
      }
    }),
  }));

export default YourNewStore;
```

**Key points:**
- `types.frozen()` stores the data as a plain JS object — no deep MST model needed. Good for read-only reference data.
- `flow()` with a generator function is required for async actions in MST. Use `yield` instead of `await`.
- The version check (`data.version > self.version`) prevents unnecessary writes. On first run, local version is `0` so any remote data wins.

---

## Step 2: Add Default State

In `versions.ts`, add your store's initial state to `defaultStoreObject`:

```typescript
export const defaultStoreObject = {
  // ... existing stores ...
  yourNewStore: { version: 0, yourData: [] },
};
```

---

## Step 3: Wire Into the Root Store

In `Store/index.ts`, make **5 additions**:

### 3a. Import
```typescript
import YourNewStore from "./YourNewStore";
```

### 3b. Add to AppStore model
```typescript
const AppStore = types.model('AppStore', {
  // ... existing stores ...
  yourNewStore: YourNewStore,
});
```

### 3c. Add snapshot listener (in `setupDataSnapshots()`)
```typescript
setupListener(self.yourNewStore, 'yourNewStore');
```

### 3d. Add rehydration (in `loadState()`)
```typescript
if (appData.yourNewStore) applySnapshot(self.yourNewStore, appData.yourNewStore);
```

### 3e. Add to init seed (in `initStores()`)
```typescript
yourNewStore: getSnapshot(self.yourNewStore),
```

---

## Step 4: Trigger the Fetch

Call `fetchData()` from the component where the data is needed. Use a `useEffect` so it fires when the user navigates to that screen:

```typescript
import React, { useContext, useEffect } from 'react';
import { observer } from 'mobx-react';
import { StoreContext } from '../Store';

const YourComponent = observer(() => {
  const { yourNewStore } = useContext(StoreContext)!;

  useEffect(() => {
    yourNewStore.fetchData();
  }, []);

  const item = yourNewStore.getItemById(42);

  return (
    // ... render using item ...
  );
});
```

**Important:** Don't `await` the fetch — it's fire-and-forget. The component renders immediately with cached data (if any), then re-renders via `observer()` if fresh data arrives.

---

## How It Works End to End

```
App Start
  └─ loadState() rehydrates from AsyncStorage
       └─ yourNewStore gets cached { version, yourData }

User navigates to screen
  └─ useEffect fires fetchData()
       ├─ Fetch succeeds, remote version > local
       │    └─ Store updates → onSnapshot fires → debounced save to AsyncStorage
       ├─ Fetch succeeds, same version
       │    └─ No-op (no unnecessary writes)
       └─ Fetch fails (offline)
            └─ Silent catch, cached data remains
```

---

## Checklist

- [ ] Remote JSON has a top-level `version` number
- [ ] Created `Store/YourNewStore.ts` with model, views, and fetch action
- [ ] Added default state to `defaultStoreObject` in `versions.ts`
- [ ] Added import to `Store/index.ts`
- [ ] Added model property to `AppStore`
- [ ] Added `setupListener()` call in `setupDataSnapshots()`
- [ ] Added `applySnapshot()` call in `loadState()`
- [ ] Added `getSnapshot()` call in `initStores()`
- [ ] Added `useEffect` fetch trigger in the consuming component
