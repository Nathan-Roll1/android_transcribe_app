set -euo pipefail
app=org.scrib.transcriber
out="$RUNNER_TEMP/scrib-evidence"
mkdir -p "$out"
trap 'adb logcat -d -t 5000 | grep -iE "scrib|fourier|transcrib|native.?heap|AndroidRuntime|lowmemory" | tail -210 > "$out/logcat.txt" || true' EXIT
adb install "$RUNNER_TEMP/scrib.apk"
adb shell getprop ro.product.cpu.abi
adb shell cat /proc/meminfo | head -5 > "$out/device-memory.txt"
adb shell dumpsys package "$app" | grep -E 'versionName|versionCode|primaryCpuAbi' | tee "$out/apk.txt"
adb shell wm size 1080x1920
adb shell wm density 270
adb shell input keyevent 82
adb shell mkdir -p /sdcard/Download
adb push "$RUNNER_TEMP/Kennedy.wav" /sdcard/Download/Kennedy.wav
adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Download/Kennedy.wav
adb push "$RUNNER_TEMP/Scenery.mp3" /sdcard/Download/Scenery.mp3
adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Download/Scenery.mp3
adb shell am start -W -n "$app/.MainActivity"
"$RUNNER_TEMP/ui/bin/python" -u scrib-ui.py "$out"
