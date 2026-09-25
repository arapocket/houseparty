// Push notifications on the phone side.
//
//   1. Ask permission (once, after you've set up your profile).
//   2. iOS hands us a token for this phone; we give it to the server.
//   3. When a notification is tapped, work out which screen to open.
//
// Until the app is signed with an Apple Developer account, iOS won't hand
// out a real token (step 2 quietly fails). Everything else works, and you
// can fake a notification in the simulator with `xcrun simctl push`.

import SwiftUI
import UserNotifications

/// Where a tapped notification should take you.
enum Route: Equatable, Sendable {
    case chat(UUID)
    case party(UUID)
    case person(UUID)

    /// Reads the "open" and "id" fields the server puts in every notification.
    init?(_ info: [AnyHashable: Any]) {
        guard let open = info["open"] as? String,
              let raw = info["id"] as? String,
              let id = UUID(uuidString: raw)
        else { return nil }
        switch open {
        case "chat": self = .chat(id)
        case "party": self = .party(id)
        case "person": self = .person(id)
        default: return nil
        }
    }

    /// The same places as links: houseparty://chat/<id>, houseparty://party/<id>,
    /// houseparty://person/<id>. Handy for testing and, later, sharing.
    init?(url: URL) {
        guard url.scheme == "houseparty", let kind = url.host(),
              let id = url.pathComponents.dropFirst().first
        else { return nil }
        self.init(["open": kind, "id": id])
    }
}

/// UIKit still delivers push tokens and taps through an "app delegate", so
/// this small class catches them and passes them to the AppModel.
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    @MainActor static var onToken: (String) -> Void = { _ in }
    @MainActor static var onRoute: (Route) -> Void = { _ in }

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken token: Data) {
        // Apple gives raw bytes; the server wants them as hex text.
        let hex = token.map { String(format: "%02x", $0) }.joined()
        Task { @MainActor in AppDelegate.onToken(hex) }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        // Expected until the app is signed with a developer account.
        print("Push registration unavailable: \(error.localizedDescription)")
    }

    // These two are called on a background thread ("nonisolated"). They read
    // what they need there and hand only the simple Route to the main thread.

    /// A notification arrived while the app is open: still show the banner.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter, willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .sound]
    }

    /// The notification was tapped.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse
    ) async {
        guard let route = Route(response.notification.request.content.userInfo) else { return }
        await MainActor.run { AppDelegate.onRoute(route) }
    }
}

enum Notifications {
    /// Shows iOS's permission prompt the first time; later calls just
    /// re-register so the server always has a fresh token.
    @MainActor
    static func enable() async {
        let center = UNUserNotificationCenter.current()
        let allowed = (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        if allowed {
            UIApplication.shared.registerForRemoteNotifications()
        }
    }
}
