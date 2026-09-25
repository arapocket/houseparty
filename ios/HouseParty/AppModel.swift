// The app-wide state: are you signed in, and who are you.
//
// Views read `phase` to decide what to show, and call the methods here to
// sign in or out. Everything else (Discover, parties, chats) keeps its own
// state in its own screen.

import Foundation
import Observation

@MainActor
@Observable
final class AppModel {
    enum Phase {
        case loading
        case signedOut
        case onboarding
        case ready
    }

    private(set) var phase: Phase = .loading
    private(set) var me: Me?

    /// Set when a notification is tapped; the tabs pick it up and navigate.
    var route: Route?

    /// This phone's push token, once iOS hands one over.
    private var pushToken: String?

    /// A client carrying the current token. Screens use this for their calls.
    private(set) var api = APIClient(token: TokenStore.load())

    /// Called once at launch: if we have a saved token, check it still works.
    func start() async {
        guard api.token != nil else {
            phase = .signedOut
            return
        }
        await refreshMe()
    }

    func refreshMe() async {
        do {
            let me = try await api.me()
            self.me = me
            phase = me.needsOnboarding ? .onboarding : .ready
        } catch APIError.signedOut {
            signOut()
        } catch {
            // Offline at launch: keep the token and let the user retry
            // rather than signing them out.
            if phase == .loading { phase = .signedOut }
        }
    }

    // MARK: Sign in

    func sendCode(to phone: String) async throws {
        try await api.startPhone(phone)
    }

    func verify(phone: String, code: String) async throws {
        let result = try await api.verifyPhone(phone, code: code)
        TokenStore.save(result.accessToken)
        api = APIClient(token: result.accessToken)
        await refreshMe()
    }

    /// iOS gave us a push token: tell the server where to reach this phone.
    func registerPush(token: String) {
        pushToken = token
        guard phase == .ready || phase == .onboarding else { return }
        Task { try? await api.registerDevice(token: token) }
    }

    func signOut() {
        // Stop this phone getting the old account's notifications. Uses the
        // old token, so it has to start before we forget it.
        if let pushToken {
            let oldAPI = api
            Task { try? await oldAPI.forgetDevice(token: pushToken) }
        }
        TokenStore.clear()
        api = APIClient(token: nil)
        me = nil
        phase = .signedOut
    }

    // MARK: Profile

    /// Used by onboarding and the profile screen. Finishing onboarding moves
    /// the app on to the main tabs by itself.
    func saveProfile(_ changes: ProfileUpdate, interests: [String]? = nil) async throws {
        var updated = try await api.updateProfile(changes)
        if let interests {
            updated = try await api.setInterests(interests)
        }
        me = updated
        phase = updated.needsOnboarding ? .onboarding : .ready
    }

    /// Returns true if the photo is live, false if it's waiting for review.
    func uploadPhoto(jpeg: Data) async throws -> Bool {
        let result = try await api.uploadPhoto(jpeg: jpeg)
        me = result.me
        return result.live
    }

    func deleteAccount() async throws {
        try await api.deleteAccount()
        signOut()
    }
}
