// wifi-heatmap-helper: reads this Mac's own Wi-Fi connection via CoreWLAN. It never scans.
//
// Signal, noise, channel and transmit rate need no permission. The SSID and BSSID need Location
// Services (macOS 14+), and macOS only grants that to an app bundle started by LaunchServices, so
// the helper ships inside "WiFi Heatmap Helper.app" (tools/build-helper.sh) and is started with `open`.
//
// Usage:
//   wifi-heatmap-helper --once
//       print one sample as JSON and exit. Run as a plain binary, SSID and BSSID are null.
//   wifi-heatmap-helper --stream <file> [--interval 2] [--parent <pid>]
//       rewrite <file> (atomically) with the latest sample every interval seconds, until <pid> exits.
//       Asks for Location permission the first time. Output goes to a file because `open` doesn't
//       pass stdout back to the caller.

import CoreLocation
import CoreWLAN
import Foundation

let bands: [Int: String] = [1: "2.4GHz", 2: "5GHz", 3: "6GHz"]
let widths: [Int: Int] = [1: 20, 2: 40, 3: 80, 4: 160, 5: 320]
let phyModes: [Int: String] = [1: "802.11a", 2: "802.11b", 3: "802.11g", 4: "802.11n", 5: "802.11ac",
                               6: "802.11ax", 7: "802.11be"]

func authName(_ s: CLAuthorizationStatus) -> String {
    switch s {
    case .notDetermined: return "not_determined"
    case .restricted: return "restricted"
    case .denied: return "denied"
    case .authorizedAlways: return "authorized"
    default: return "unknown"
    }
}

func sample(location: String) -> [String: Any] {
    var d: [String: Any] = ["ts": Date().timeIntervalSince1970, "location": location, "pid": Int(getpid())]
    guard let i = CWWiFiClient.shared().interface() else {
        d["connected"] = false
        d["error"] = "no Wi-Fi interface"
        return d
    }
    let rssi = i.rssiValue()     // 0 when not associated
    let ch = i.wlanChannel()
    d["iface"] = i.interfaceName ?? NSNull()
    d["power"] = i.powerOn()
    d["connected"] = i.powerOn() && rssi != 0 && ch != nil
    guard d["connected"] as? Bool == true, let ch = ch else { return d }
    d["rssi"] = rssi
    d["noise"] = i.noiseMeasurement()
    d["channel"] = ch.channelNumber
    d["band"] = bands[ch.channelBand.rawValue] ?? NSNull()
    d["width"] = widths[ch.channelWidth.rawValue] ?? NSNull()
    d["tx_rate"] = i.transmitRate()
    d["phy"] = phyModes[i.activePHYMode().rawValue] ?? NSNull()
    d["ssid"] = i.ssid() ?? NSNull()
    d["bssid"] = i.bssid() ?? NSNull()
    return d
}

func json(_ d: [String: Any]) -> Data {
    try! JSONSerialization.data(withJSONObject: d, options: [.sortedKeys])
}

func arg(_ name: String) -> String? {
    let a = CommandLine.arguments
    guard let k = a.firstIndex(of: name), k + 1 < a.count else { return nil }
    return a[k + 1]
}

if CommandLine.arguments.contains("--once") {
    let status = authName(CLLocationManager().authorizationStatus)
    FileHandle.standardOutput.write(json(sample(location: status)))
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
    exit(0)
}

let out = arg("--stream") ?? ""
if out.isEmpty {
    FileHandle.standardError.write("usage: wifi-heatmap-helper --once | --stream <file> [--interval 2] [--parent <pid>]\n"
        .data(using: .utf8)!)
    exit(2)
}
let interval = max(0.5, Double(arg("--interval") ?? "") ?? 2.0)
let parent = arg("--parent").flatMap { pid_t($0) }

class Streamer: NSObject, CLLocationManagerDelegate {
    let manager = CLLocationManager()
    var timer: Timer?
    override init() {
        super.init()
        manager.delegate = self   // the delegate soon gets the real status
        // Until that first callback the status reads "not determined" even when it's allowed, so
        // samples start there (or after 1 s, in case it never comes).
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { self.begin() }
    }
    func locationManagerDidChangeAuthorization(_ m: CLLocationManager) {
        if m.authorizationStatus == .notDetermined { m.requestWhenInUseAuthorization() }
        begin()
    }
    func begin() {
        guard timer == nil else { return }
        tick()
        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { _ in self.tick() }
    }
    func tick() {
        if let p = parent, kill(p, 0) != 0 && errno == ESRCH { exit(0) }
        try? json(sample(location: authName(manager.authorizationStatus)))
            .write(to: URL(fileURLWithPath: out), options: .atomic)
    }
}

let streamer = Streamer()
RunLoop.main.run()
