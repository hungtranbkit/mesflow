# MESFlow v65.8.44.2

- Web Kiosk: add reworkable defect flow matching ESP32 kiosk.
- Finish flow: enter good/defect -> 1 OK / 2 Edit / 3 Reworkable defect.
- Rework screen validates rework_qty <= defect_qty.
- Final confirmation: 1 OK / 2 Edit.
- Sends rework_qty to /api/kiosk-web/finish and shows real scrap = defect - rework.
- Keyboard shortcuts 1/2/3 work on confirmation screens.
