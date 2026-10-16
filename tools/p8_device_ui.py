#!/usr/bin/env python3
"""Opt-in production CameraX/OS-WorkManager UI phases in the separate P8 QA UID.

Never clears data, imports media, changes connectivity, or accesses a different
app. --r8-apk optionally updates ONLY the confirmed QA package after stopping it.
Confirm target/packages/scene with the owner before using this.
Private capture bytes stay on the phone; output contains redacted metadata only.
"""
import argparse
import json
import shlex
import subprocess
import time
import hashlib
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGE = "in.kaushalpramaan.app.p8validation"
TEST_PACKAGE = PACKAGE + ".test"
ACTIVITY = "in.kaushalpramaan.app.MainActivity"
TEST_CLASS = "in.kaushalpramaan.app.P8ValidationUiTest"
TERMINAL = {"COMPLETED", "PARTIAL"}


class Device:
    def __init__(self, serial):
        self.serial = serial

    def adb(self, *args, check=True):
        return subprocess.run(["adb", "-s", self.serial, *args], text=True,
                              capture_output=True, check=check).stdout.strip()

    def shell(self, *args):
        return self.adb("shell", shlex.join(args))

    def state(self):
        # One safely quoted remote command; no repeated instrumentation starts,
        # which themselves restart the target and invalidate recovery evidence.
        text = self.shell("run-as", PACKAGE, "cat", "files/p8-validation-state.json")
        result = json.loads(text)
        assert result.get("package") == PACKAGE and "error" not in result, result
        return result

    def ui_command(self, phase, task="T2", seconds=30, hold=0):
        return ["adb", "-s", self.serial, "shell", "am", "instrument", "-w", "-r",
                "-e", "class", TEST_CLASS, "-e", "p8Phase", phase,
                "-e", "p8Task", task, "-e", "p8VideoSeconds", str(seconds),
                "-e", "p8HoldMs", str(hold), TEST_PACKAGE + "/androidx.test.runner.AndroidJUnitRunner"]

    def tap_accessible(self, matches):
        """Real touch input for the independently shrunk APK; no shared test ABI."""
        def bounds(node):
            return list(map(int, re.findall(r"\d+", node.attrib["bounds"])))
        for _ in range(12):
            path = "/data/local/tmp/parakh-p8-validation.xml"
            self.shell("uiautomator", "dump", path)
            tree = ET.fromstring(self.adb("exec-out", "cat", path))
            nodes = [n for n in tree.iter("node") if n.get("package") == PACKAGE]
            assert nodes, "Refusing input outside the confirmed QA app"
            node = next((n for n in nodes if matches(n)), None)
            if node is not None:
                left, top, right, bottom = bounds(node)
                self.shell("input", "tap", str((left + right) // 2), str((top + bottom) // 2))
                return
            scroll = next((n for n in nodes if n.get("scrollable") == "true"), None)
            assert scroll is not None, "Requested QA control is not visible or scrollable"
            left, top, right, bottom = bounds(scroll)
            x = (left + right) // 2
            self.shell("input", "swipe", str(x), str(int(top + (bottom-top)*.8)), str(x), str(int(top + (bottom-top)*.25)), "300")
        raise AssertionError("Requested QA control not found after scrolling")


def poll(read, condition, timeout=120):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        try:
            latest = read()
            if condition(latest):
                return latest
        except (ValueError, subprocess.CalledProcessError):
            pass  # Observer not started yet / atomic replacement in progress.
        time.sleep(0.25)
    raise AssertionError(f"Timed out waiting for device state; latest={latest}")


def assert_offline(state):
    assert state["airplaneMode"] == 1 and state["internetNetworkCount"] == 0, "Phone is not offline"


def run_phase(device, args, log):
    command = device.ui_command(args.phase, args.task, args.seconds)
    with log.open("w") as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=300)
    transcript = log.read_text()
    assert result.returncode == 0 and "OK (1 test)" in transcript, f"UI phase failed: {log}"
    # Android finishes the instrumented Activity; reopen the normal product so
    # its ordinary process/OS worker and the read-only observer can continue.
    device.shell("am", "start", "-W", "-n", PACKAGE + "/" + ACTIVITY)
    return poll(device.state, lambda s: "assessmentId" in s and
                (args.phase != "seal" or s.get("sealState") == "READY_TO_SYNC") and
                (args.phase != "synced" or s.get("synced") is True))


def recover(device, args, log):
    initial = device.state()
    known_ids = {e["id"] for e in initial.get("evidence", [])}
    with log.open("w") as output:
        process = subprocess.Popen(device.ui_command("video", args.task, args.seconds, hold=60_000),
                                   stdout=output, stderr=subprocess.STDOUT)
        try:
            before = poll(device.state, lambda s: any(
                e["id"] not in known_ids and e.get("status") == "RUNNING" for e in s.get("evidence", [])) and
                "p8_phase=video" in log.read_text(), timeout=args.seconds + 90)
            if args.require_offline:
                assert_offline(before)
            item = next(e for e in before["evidence"] if e["id"] not in known_ids and e.get("status") == "RUNNING")
            assert any(w["state"] == "RUNNING" and w["network"] == "NOT_REQUIRED" for w in item["work"])
            args.out.with_suffix(".before-stop.json").write_text(json.dumps(before, indent=2) + "\n")
            # Exact QA package only; no destructive data reset, scheduler test
            # override, fake engine, or injected Room/WorkerFactory dependency.
            device.shell("am", "force-stop", PACKAGE)
            process.wait(timeout=20)
            if args.r8_apk:
                # A separate shrunk runtime check avoids weakening R8 merely to
                # retain the test framework's cross-APK Compose/coroutine ABI.
                sdk = Path(os.environ.get("ANDROID_HOME", os.environ.get("ANDROID_SDK_ROOT", str(Path.home() / "Android/Sdk"))))
                aapt = sdk / "build-tools/36.0.0/aapt2"
                badging = subprocess.run([str(aapt), "dump", "badging", str(args.r8_apk)],
                                        text=True, capture_output=True, check=True).stdout
                assert re.search(r"^package: name='" + re.escape(PACKAGE) + r"' ", badging), "Wrong APK package"
                install = device.adb("install", "-r", str(args.r8_apk))
                assert "Success" in install, install
            launch = device.shell("am", "start", "-W", "-n", PACKAGE + "/" + ACTIVITY)
            assert "Status: ok" in launch, launch
            def completed(state):
                match = next((e for e in state.get("evidence", []) if e["id"] == item["id"]), None)
                return state.get("pid") != before["pid"] and match is not None and match.get("status") in TERMINAL and any(
                    w["state"] == "SUCCEEDED" for w in match["work"])
            after = poll(device.state, completed, timeout=180)
            recovered = next(e for e in after["evidence"] if e["id"] == item["id"])
            # A terminal PARTIAL state can honestly contain an unavailable model.
            # That is valid product behavior, but cannot pass native/R8 execution
            # validation without evidence that BOTH engines actually ran samples.
            for component in ("quality", "hands"):
                analysis = recovered["result"][component]
                assert analysis["status"] in TERMINAL and analysis["coverage"]["analysedSamples"] > 0, f"{component} did not execute"
            assert before["assessmentId"] == after["assessmentId"]
            assert all(recovered[k] == item[k] for k in ("id", "sha256", "revisionNumber", "durationMs", "bytes"))
            if args.require_offline:
                assert_offline(after)
            return {"beforeStop": before, "afterRecovery": after, "interruptedInvocation": "EXPECTED_PROCESS_STOP",
                    "recoveryApkSha256": hashlib.sha256(args.r8_apk.read_bytes()).hexdigest() if args.r8_apk else None}
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=20)


def retry_recovery(device, args):
    initial = device.state()
    item = next(e for e in initial["evidence"] if e["taskId"] == args.task and e.get("status") in {"PARTIAL", "FAILED", "UNAVAILABLE"})
    device.shell("am", "start", "-W", "-n", PACKAGE + "/" + ACTIVITY)
    device.tap_accessible(lambda n: n.get("text", "").startswith(args.task + " —"))
    device.tap_accessible(lambda n: n.get("content-desc") == "Video evidence item")
    device.tap_accessible(lambda n: n.get("text") == "Retry analysis")
    before = poll(device.state, lambda s: any(e["id"] == item["id"] and e.get("generation") != item["generation"] and
                  e.get("status") == "RUNNING" for e in s["evidence"]), timeout=30)
    args.out.with_suffix(".before-stop.json").write_text(json.dumps(before, indent=2) + "\n")
    if args.require_offline:
        assert_offline(before)
    device.shell("am", "force-stop", PACKAGE)
    assert "Status: ok" in device.shell("am", "start", "-W", "-n", PACKAGE + "/" + ACTIVITY)
    after = poll(device.state, lambda s: s["pid"] != before["pid"] and any(e["id"] == item["id"] and
                 e.get("status") in TERMINAL and any(w["state"] == "SUCCEEDED" for w in e["work"]) for e in s["evidence"]), timeout=180)
    recovered = next(e for e in after["evidence"] if e["id"] == item["id"])
    assert all(recovered[k] == item[k] for k in ("id", "sha256", "revisionNumber", "durationMs", "bytes"))
    for component in ("quality", "hands"):
        analysis = recovered["result"][component]
        assert analysis["status"] in TERMINAL and analysis["coverage"]["analysedSamples"] > 0, f"{component} did not execute"
    if args.require_offline:
        assert_offline(after)
    return {"beforeStop": before, "afterRecovery": after, "realAccessibilityRetry": True}


def sync_interrupt(device, args):
    initial = device.state()
    assert_offline(initial)
    assert initial["sealState"] == "READY_TO_SYNC" and not initial["synced"]
    assert all(w["network"] == "CONNECTED" and w["state"] == "ENQUEUED" for w in initial["syncWork"])
    before = poll(device.state, lambda s: not s["synced"] and any(
        row["kind"] == "EVIDENCE" and row["state"] == "UPLOADING" and row["uploadedBytes"] > 0
        for row in s["outbox"]), timeout=180)
    args.out.with_suffix(".before-stop.json").write_text(json.dumps(before, indent=2) + "\n")
    assert before["serverAssessmentId"] is not None
    device.shell("am", "force-stop", PACKAGE)
    assert "Status: ok" in device.shell("am", "start", "-W", "-n", PACKAGE + "/" + ACTIVITY)
    after = poll(device.state, lambda s: s["synced"] and s["pid"] != before["pid"], timeout=180)
    assert before["serverAssessmentId"] == after["serverAssessmentId"]
    assert before["assessmentId"] == after["assessmentId"]
    assert [e["sealedSnapshot"] for e in initial["evidence"]] == [e["sealedSnapshot"] for e in after["evidence"]]
    return {"beforeConnectivity": initial, "beforeStop": before, "afterRecovery": after}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--phase", required=True, choices=["intake", "photo-retake-delete", "video", "retry", "inspect", "process", "seal", "sealed-preview", "synced", "sync-interrupt", "check-updates", "recovery", "retry-recovery", "state"])
    parser.add_argument("--task", default="T2", choices=["T1", "T2", "T3", "T4", "T5"])
    parser.add_argument("--seconds", default=30, type=int, choices=range(2, 61), metavar="2..60")
    parser.add_argument("--require-offline", action="store_true")
    parser.add_argument("--r8-apk", type=Path, help="Separately shrunk QA APK to install -r after the controlled process stop")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.r8_apk:
        assert args.phase == "recovery" and args.r8_apk.is_file(), "--r8-apk requires a recovery phase and an existing APK"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    device = Device(args.serial)
    for package in (PACKAGE, TEST_PACKAGE):
        assert device.shell("pm", "path", package).startswith("package:"), f"Not installed: {package}"
    report = {"package": PACKAGE, "phase": args.phase,
              "model": device.shell("getprop", "ro.product.model"),
              "androidVersion": device.shell("getprop", "ro.build.version.release")}
    started = time.monotonic()
    try:
        if args.require_offline and args.phase != "intake":
            # Connectivity teardown is asynchronous. Wait for actual evidence of
            # disconnection, never treat the settings toggle as proof of offline.
            assert_offline(poll(device.state, lambda s: s.get("airplaneMode") == 1 and
                               s.get("internetNetworkCount") == 0, timeout=30))
        if args.phase == "recovery":
            report.update(recover(device, args, args.out.with_suffix(".log")))
        elif args.phase == "retry-recovery":
            report.update(retry_recovery(device, args))
        elif args.phase == "sync-interrupt":
            report.update(sync_interrupt(device, args))
        elif args.phase == "process":
            device.shell("am", "start", "-W", "-n", PACKAGE + "/" + ACTIVITY)
            device.tap_accessible(lambda n: n.get("text") == "Preview and submit")
            device.tap_accessible(lambda n: n.get("text") == "Optimize evidence")
            state = poll(device.state, lambda s: s.get("sealState") == "FINAL_REVIEW_READY", timeout=180)
            if args.require_offline:
                assert_offline(state)
            report["state"] = state
        else:
            state = device.state() if args.phase == "state" else run_phase(device, args, args.out.with_suffix(".log"))
            if args.require_offline:
                assert_offline(state)
            report["state"] = state
        report["verdict"] = "PASS"
    except Exception as error:
        report["verdict"] = "FAIL"
        report["error"] = str(error)
        raise
    finally:
        report["wallSeconds"] = round(time.monotonic() - started, 3)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"{args.phase}: {report['verdict']} ({args.out})")


if __name__ == "__main__":
    main()
