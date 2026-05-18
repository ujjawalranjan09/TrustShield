package com.trustshield.sdk

import android.content.Context
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Build
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.TextView

class OverlayWarning(private val context: Context) {

    private var windowManager: WindowManager? = null
    private var overlayView: View? = null

    fun showWarning(warningEn: String, warningHi: String, reason: String) {
        windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager

        // Mock inflating view
        // overlayView = LayoutInflater.from(context).inflate(R.layout.warning_overlay, null)

        // For demonstration, mock the view creation
        overlayView = View(context)
        overlayView?.setBackgroundColor(Color.parseColor("#80000000")) // Semi-transparent black

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else
                WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        )
        params.gravity = Gravity.CENTER

        // Mock setting text and buttons
        // val textEn = overlayView?.findViewById<TextView>(R.id.text_en)
        // val textHi = overlayView?.findViewById<TextView>(R.id.text_hi)
        // val btnDismiss = overlayView?.findViewById<Button>(R.id.btn_dismiss)
        // val btnReport = overlayView?.findViewById<Button>(R.id.btn_report)

        /*
        btnDismiss?.setOnLongClickListener {
            dismiss()
            true
        }
        btnReport?.setOnClickListener {
            // Call API POST /v1/report
            dismiss()
        }
        */

        windowManager?.addView(overlayView, params)
    }

    fun dismiss() {
        if (overlayView != null) {
            windowManager?.removeView(overlayView)
            overlayView = null
        }
    }
}
