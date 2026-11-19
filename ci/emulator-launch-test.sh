#!/usr/bin/env bash
# Emulator launch test for Phone Node Waker.
#
# Installs the debug APK, launches MainActivity, and verifies that
# the app process is alive, MainActivity is the top resumed
# activity, and logcat contains no FATAL EXCEPTION for the app.
# A screenshot of the main screen is captured for visual inspection
# before handover.
#
# This script exists as a file (not inline in the workflow) because
# reactivecircus/android-emulator-runner executes an inline
# `script:` block line-by-line in separate shells, so shell state
# and `exit` do not work there.
set -u
cd "$(dirname "$0")/.."

APK=app/build/outputs/apk/debug/app-debug.apk
PKG=dev.moriya.phonenode.waker
FAIL=0

note_fail() { echo "LAUNCH-TEST FAILURE: $1"; FAIL=1; }

top_activity() {
  adb shell dumpsys activity activities 2>/dev/null | grep "topResumedActivity" | head -1
}

screencap() { # $1 = output png name
  adb exec-out screencap -p > "$1" 2>/dev/null || adb shell screencap -p "/sdcard/$1" && adb pull "/sdcard/$1" "$1" >/dev/null 2>&1
  if [ -s "$1" ]; then echo "screenshot saved: $1 ($(stat -c%s "$1") bytes)"; else echo "WARNING: screenshot $1 empty/missing"; fi
}

adb root || true
sleep 2
adb install -r "$APK" || note_fail "adb install failed"
adb shell pm grant $PKG android.permission.POST_NOTIFICATIONS || true

adb logcat -c || true
adb shell am start -n $PKG/.MainActivity
sleep 5
PID=$(adb shell pidof $PKG | tr -d '\r\n')
echo "PID after MainActivity: '$PID'"
[ -n "$PID" ] || note_fail "app process not alive after MainActivity launch"
TOP=$(top_activity)
echo "top after MainActivity launch: $TOP"
if echo "$TOP" | grep -q "$PKG/.MainActivity"; then
  echo "OK: MainActivity is top resumed activity"
else
  note_fail "MainActivity is not the top resumed activity"
fi
screencap screenshot-main.png

adb shell dumpsys activity activities > dumpsys-activities.txt 2>&1 || true
adb logcat -d -v threadtime > logcat.txt 2>&1 || true
adb shell uiautomator dump /sdcard/window_dump.xml >/dev/null 2>&1 || true
adb pull /sdcard/window_dump.xml window_dump.xml >/dev/null 2>&1 || true

if grep -q "FATAL EXCEPTION" logcat.txt && grep -A3 "FATAL EXCEPTION" logcat.txt | grep -q "$PKG"; then
  note_fail "FATAL EXCEPTION for $PKG in logcat"
fi

echo "LAUNCH_TEST_FAIL=$FAIL"
exit $FAIL
