import Cocoa

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

let profile = try JSONDecoder().decode(MenuProfile.self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let controller = MenuController(profile: profile)
let fakeLauncher = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
try "#!/bin/sh\nprintf 'http://127.0.0.1:9231\\n'\n".write(to: fakeLauncher, atomically: true, encoding: .utf8)
try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: fakeLauncher.path)
let fakeProfile = MenuProfile(launcher: fakeLauncher.path, label: profile.label,
                              domain: profile.domain, logs: profile.logs, system: false, portFile: nil)
let portController = MenuController(profile: fakeProfile)
var customURL = ""
portController.openURL = { customURL = $0.absoluteString; return true }
portController.showError = { fail($0) }
portController.openWebsite()
try FileManager.default.removeItem(at: fakeLauncher)
if customURL != "http://127.0.0.1:9231" { fail("Configured browser port was ignored") }
var urls: [String] = []
var didQuit = false
controller.openURL = { urls.append($0.absoluteString); return true }
controller.showError = { fail($0) }
controller.quitApplication = { didQuit = true }
app.delegate = controller
let deadline = Date().addingTimeInterval(70)
var phase = "initial"

func click(_ title: String) {
    let index = controller.menu.indexOfItem(withTitle: title)
    if index < 0 || !controller.menu.item(at: index)!.isEnabled { fail("Menu unavailable: \(title)") }
    controller.menu.performActionForItem(at: index)
}

let testTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { timer in
    if Date() > deadline { fail("Timed out during \(phase)") }
    if controller.busy { return }
    switch phase {
    case "initial":
        if !controller.running { fail("Service must initially be running") }
        if controller.statusItem?.menu !== controller.menu { fail("Menu is not attached to status bar") }
        click("停止服务")
        phase = "stopped"
    case "stopped":
        if controller.running { fail("Stop did not stop the service") }
        click("打开网页界面")
        click("启动服务")
        phase = "started"
    case "started":
        // launchd may still be starting the process after bootstrap succeeds.
        if !controller.running { controller.refreshStatus(); return }
        click("刷新状态")
        phase = "refreshed"
    default:
        if !controller.running { fail("Started service did not remain running") }
        click("打开日志目录")
        click("退出菜单栏控件")
        if !didQuit { fail("Quit action was not called") }
        if urls.first != "http://127.0.0.1:8130" { fail("Wrong browser URL") }
        if urls.last != URL(fileURLWithPath: profile.logs, isDirectory: true).absoluteString {
            fail("Wrong log directory")
        }
        print("{\"native_menu_widgets\":true,\"stop_start_widgets\":true,\"browser_url\":\"http://127.0.0.1:8130\",\"quit_action\":true}")
        timer.invalidate()
        app.terminate(nil)
    }
}
app.run()
