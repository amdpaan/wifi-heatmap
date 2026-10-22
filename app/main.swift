// "Wi-Fi Heatmap.app": opens the dashboard in your browser. If it isn't answering, asks launchd to start
// the login agent (./install.sh --agent) and waits a few seconds; if that doesn't help, says what to do.
import AppKit

let dashboard = URL(string: "http://127.0.0.1:8766/")!
let label = "com.wifiheatmap.serve"

func answering() -> Bool {
    var ok = false
    let done = DispatchSemaphore(value: 0)
    var req = URLRequest(url: URL(string: "api/state", relativeTo: dashboard)!)
    req.timeoutInterval = 1.5
    URLSession.shared.dataTask(with: req) { _, resp, _ in
        ok = (resp as? HTTPURLResponse)?.statusCode == 200
        done.signal()
    }.resume()
    _ = done.wait(timeout: .now() + 2)
    return ok
}

func startAgent() {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/bin/launchctl")
    p.arguments = ["kickstart", "gui/\(getuid())/\(label)"]
    try? p.run()
    p.waitUntilExit()
}

var up = answering()
if !up {
    startAgent()
    for _ in 0..<20 where !up {
        usleep(300_000)
        up = answering()
    }
}
if up {
    NSWorkspace.shared.open(dashboard)
} else {
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    app.activate(ignoringOtherApps: true)
    let alert = NSAlert()
    alert.messageText = "The wifi-heatmap dashboard isn't running"
    alert.informativeText = "To keep it running from login, run ./install.sh --agent once in the wifi-heatmap folder. "
        + "Or start it for now with: wifi-heatmap serve"
    alert.runModal()
}
