// Takes a full-page screenshot of a URL with WebKit (for the README's demo screenshots).
// Usage: screenshot <url> <width> <height> <out.png> [light|dark] [javascript to run first]
import AppKit
import WebKit

let a = CommandLine.arguments
guard a.count >= 5, let url = URL(string: a[1]), let w = Double(a[2]), let h = Double(a[3]) else {
    FileHandle.standardError.write("usage: screenshot <url> <width> <height> <out.png> [light|dark] [js]\n".data(using: .utf8)!)
    exit(2)
}
let out = a[4], dark = a.count > 5 && a[5] == "dark", js = a.count > 6 ? a[6] : ""

let app = NSApplication.shared
app.setActivationPolicy(.prohibited)
let view = WKWebView(frame: NSRect(x: 0, y: 0, width: w, height: h))
view.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
window.appearance = view.appearance
window.contentView = view
view.load(URLRequest(url: url))

func after(_ s: Double, _ f: @escaping @MainActor () -> Void) {
    DispatchQueue.main.asyncAfter(deadline: .now() + s) { MainActor.assumeIsolated { f() } }
}

after(2.5) {   // let the page fetch its data and draw
    // wrapped in a function so it can be statements, and so nothing (a Promise) comes back to Swift
    view.evaluateJavaScript("(() => { \(js) })(); 0") { _, err in
        if let err = err { FileHandle.standardError.write("javascript: \(err)\n".data(using: .utf8)!); exit(1) }
        after(1.2) {
            view.evaluateJavaScript("document.documentElement.scrollHeight") { v, _ in
                let full = max(h, (v as? Double) ?? h)
                window.setContentSize(NSSize(width: w, height: full))
                view.frame = NSRect(x: 0, y: 0, width: w, height: full)
                after(0.6) {
                    let cfg = WKSnapshotConfiguration()
                    cfg.rect = NSRect(x: 0, y: 0, width: w, height: full)
                    view.takeSnapshot(with: cfg) { img, _ in
                        guard let img = img, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
                              let png = rep.representation(using: .png, properties: [:]) else { exit(1) }
                        try? png.write(to: URL(fileURLWithPath: out))
                        exit(0)
                    }
                }
            }
        }
    }
}
app.run()
