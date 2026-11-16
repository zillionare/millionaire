import Cocoa

let application = NSApplication.shared
let identifier = Bundle.main.bundleIdentifier ?? "ai.quantide.millionaire.controller"
let others = NSRunningApplication.runningApplications(withBundleIdentifier: identifier)
    .filter { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier }
if CommandLine.arguments.contains("--quit") {
    others.forEach { $0.terminate() }
    let deadline = Date().addingTimeInterval(8)
    while others.contains(where: { !$0.isTerminated }) && Date() < deadline {
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))
    }
    if others.contains(where: { !$0.isTerminated }) { exit(1) }
    exit(0)
}
if !others.isEmpty { exit(0) }

do {
    let file = Bundle.main.bundleURL.deletingLastPathComponent()
        .appendingPathComponent("controller.json")
    let profile = try JSONDecoder().decode(MenuProfile.self, from: Data(contentsOf: file))
    let controller = MenuController(profile: profile)
    application.setActivationPolicy(.accessory)
    application.delegate = controller
    application.run()
} catch {
    let alert = NSAlert()
    alert.messageText = "Millionaire 菜单栏控件尚未配置"
    alert.informativeText = "请重新运行安装脚本。\n\(error.localizedDescription)"
    alert.runModal()
    exit(1)
}
