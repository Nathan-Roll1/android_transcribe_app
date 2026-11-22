set -euo pipefail
app=dev.notune.transcribe
model=Fourier-2B-Q8_0.gguf
adb install -r app/build/outputs/apk/fdroid/debug/*.apk
adb shell getprop ro.build.version.sdk
adb shell getprop ro.product.cpu.abi
adb shell "run-as $app mkdir -p files/models"
adb shell -T "run-as $app sh -c 'cat > files/models/$model'" < "$RUNNER_TEMP/$model"
adb shell -T "run-as $app sh -c 'cat > files/fixture.wav'" < "$RUNNER_TEMP/jfk.wav"
echo "$model" | adb shell -T "run-as $app sh -c 'cat > files/active_model'"
adb shell "run-as $app sha256sum files/models/$model" | grep 6a7c419bd571f7b0e21da2d5ab1e3a1a3938a83470d622be57427af98f322981
adb shell input keyevent 82
adb shell am start -W -a android.intent.action.VIEW -t audio/wav -d "file:///data/user/0/$app/files/fixture.wav" -n "$app/.TranscribeFileActivity"
for attempt in $(seq 1 50); do
  adb shell uiautomator dump /sdcard/screen.xml >/dev/null || true
  adb exec-out cat /sdcard/screen.xml > "$RUNNER_TEMP/screen.xml" || true
  if python3 verification/check-screen.py "$RUNNER_TEMP/screen.xml"; then exit 0; fi
  sleep 4
done
adb logcat -d -t 1000 | grep -iE 'transcribe|fourier|fatal|oom|exception|denied' | tail -100 || true
exit 1
