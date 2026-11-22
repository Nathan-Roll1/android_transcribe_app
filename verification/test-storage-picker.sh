set -euo pipefail
app=dev.notune.transcribe
model=Fourier-2B-Q8_0.gguf
sha=6a7c419bd571f7b0e21da2d5ab1e3a1a3938a83470d622be57427af98f322981
out="$RUNNER_TEMP/picker-evidence"
mkdir -p "$out"
trap 'adb logcat -d -t 1200 | grep -iE "transcribe|documentsui|fourier|fatal|oom|exception|denied" | tail -110 > "$out/logcat.txt" || true' EXIT
adb install app/build/outputs/apk/fdroid/debug/*.apk
adb shell getprop ro.product.cpu.abi
adb shell getprop ro.build.version.sdk
adb shell wm size 1080x2400
adb shell wm density 320
adb shell input keyevent 82
adb shell "run-as $app sh -c '[ ! -e files/models/$model ] && [ ! -s files/active_model ]'"
adb shell df -h /data
adb push "$RUNNER_TEMP/$model" "/sdcard/Download/$model"
adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file:///sdcard/Download/$model"
adb shell am start -W -n "$app/.MainActivity"
python3 verification/storage-picker.py import
# Only read the imported model and selected marker; neither is seeded.
actual=$(adb shell "run-as $app cat files/active_model" | tr -d '\r\n')
test "$actual" = "$model"
size=$(adb shell "run-as $app stat -c %s files/models/$model" | tr -d '\r\n')
test "$size" = 2185030848
actual_sha=$(adb shell "run-as $app sha256sum files/models/$model" | awk '{print $1}')
test "$actual_sha" = "$sha"
printf 'active=%s\nbytes=%s\nsha256=%s\n' "$actual" "$size" "$actual_sha" | tee "$out/selected.txt"
# Use the ordinary audio VIEW intent with a public reference clip. The debug
# harness stages this small WAV only; private model storage remains read-only.
adb shell -T "run-as $app sh -c 'cat > files/fixture.wav'" < "$RUNNER_TEMP/jfk.wav"
adb shell am force-stop "$app"
adb shell am start -W -a android.intent.action.VIEW -t audio/wav -d "file:///data/user/0/$app/files/fixture.wav" -n "$app/.TranscribeFileActivity"
python3 verification/storage-picker.py transcribe
