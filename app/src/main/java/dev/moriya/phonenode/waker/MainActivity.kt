package dev.moriya.phonenode.waker

import android.app.Activity
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import com.google.firebase.messaging.FirebaseMessaging

/**
 * Trial UI: shows the FCM registration token (the VM-side sender
 * needs it once) and offers a local "wake" button that exercises
 * the same cross-app NodeService start the FCM handler performs,
 * so the start edge can be verified without Firebase in the loop.
 */
class MainActivity : Activity() {

    private lateinit var tokenView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(48, 48, 48, 48)
        }
        tokenView = TextView(this).apply {
            textSize = 13f
            text = "token: (loading)"
        }
        layout.addView(tokenView)
        layout.addView(Button(this).apply {
            text = "Wake phone-node now (local test)"
            setOnClickListener {
                val ok = WakerService.wakeNode(this@MainActivity)
                Toast.makeText(
                    this@MainActivity,
                    if (ok) "NodeService start requested" else "Start failed",
                    Toast.LENGTH_SHORT
                ).show()
            }
        })
        setContentView(layout)
        refreshToken()
    }

    override fun onResume() {
        super.onResume()
        refreshToken()
    }

    private fun refreshToken() {
        val prefs = getSharedPreferences(WakerService.PREFS, MODE_PRIVATE)
        prefs.getString(WakerService.KEY_TOKEN, null)?.let {
            tokenView.text = "token: $it"
        }
        FirebaseMessaging.getInstance().token
            .addOnCompleteListener { task ->
                if (task.isSuccessful) {
                    val token = task.result
                    prefs.edit().putString(WakerService.KEY_TOKEN, token).apply()
                    tokenView.text = "token: $token"
                } else {
                    tokenView.text = "token: (fetch failed: ${task.exception})"
                }
            }
    }
}
