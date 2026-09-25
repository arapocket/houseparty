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

    func signOut() {
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

    func deleteAccount() async throws {
        try await api.deleteAccount()
        signOut()
    }
}
