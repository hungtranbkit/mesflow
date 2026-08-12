# MESFlow v65.5.6

## Template creation UI
- Added a permanently visible "Tạo Template mới" form on the Template page.
- The form sends POST /api/templates with code, name, product, version and active status.
- After successful creation, the list reloads and the Template structure builder opens automatically.
- Existing edit, delete, structure builder and instantiate-to-PO actions remain available.
- Added explicit loading and error states to the create button.
