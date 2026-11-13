# phone-node-waker

Trial app for the FCM revival path of phone-node. When the phone's
power management or the low-memory killer sweeps the phone-node main
app (and its helper) away — as happened on the ZTE Libero 5G IV on
2026-11-13, when even Tailscale died with them — a high-priority
FCM data message can still arrive, because delivery runs through
Google Play services. This app receives that message and performs
the same resurrection call the helper app uses: an explicit
startForegroundService for dev.moriya.phonenode/.NodeService.

The phone-node app itself is untouched by this design.

## Layout

- `WakerService` — FirebaseMessagingService; on data {action=wake}
  it starts NodeService. The token is kept in SharedPreferences.
- `MainActivity` — shows the FCM token (the VM-side sender needs it
  once) and a local wake button that exercises the same start call
  without Firebase in the loop.

## Build

GitHub Actions (Gradle cannot run on the Muse VM). Requires
`app/google-services.json` from the Firebase console (project
config, not a credential) and the pinned-signing secrets
SIGNING_KEYSTORE_B64 / SIGNING_STORE_PASS / SIGNING_KEY_ALIAS /
SIGNING_KEY_PASS.
