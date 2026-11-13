package dev.moriya.phonenode.waker

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.util.Log
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

/**
 * Receives high-priority FCM data messages and resurrects the
 * phone-node main app by starting its NodeService — the exact call
 * the helper app already uses (HelperService.resurrectMainApp), so
 * the only new link in the chain is the FCM delivery itself, which
 * arrives via Google Play services and therefore survives the
 * system-level app sweeps that kill the main app and the helper.
 */
class WakerService : FirebaseMessagingService() {

    override fun onMessageReceived(message: RemoteMessage) {
        Log.i(TAG, "FCM message: from=${message.from} data=${message.data}")
        if (message.data["action"] == "wake") {
            wakeNode(this)
        }
    }

    override fun onNewToken(token: String) {
        getSharedPreferences(PREFS, MODE_PRIVATE)
            .edit().putString(KEY_TOKEN, token).apply()
        Log.i(TAG, "FCM token updated")
    }

    companion object {
        private const val TAG = "WakerService"
        const val PREFS = "waker-state"
        const val KEY_TOKEN = "fcm_token"

        /** Identical to the helper app's resurrection call. */
        fun wakeNode(context: Context): Boolean {
            val intent = Intent().apply {
                component = ComponentName(
                    "dev.moriya.phonenode",
                    "dev.moriya.phonenode.NodeService"
                )
            }
            return try {
                context.startForegroundService(intent)
                Log.i(TAG, "NodeService start requested")
                true
            } catch (e: Exception) {
                Log.w(TAG, "NodeService start failed: $e")
                false
            }
        }
    }
}
