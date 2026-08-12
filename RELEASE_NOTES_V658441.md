# MESFlow v65.8.44.1

## Hotfix: Overview blank after browser reload

- Fixed initial page bootstrap order.
- `app.js` no longer calls `renderOverview()` before `pages/overview.js` is loaded.
- Initial Overview navigation now runs after all page scripts are available.
- Keeps normal tab navigation and Overview 15-second refresh behavior unchanged.
