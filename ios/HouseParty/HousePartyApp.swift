import SwiftUI

@main
struct HousePartyApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .task { await model.start() }
        }
    }
}

/// Picks the screen for where you are: signing in, setting up, or in.
struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        switch model.phase {
        case .loading:
            ProgressView()
        case .signedOut:
            SignInView()
        case .onboarding:
            OnboardingView()
        case .ready:
            MainTabs()
        }
    }
}

struct MainTabs: View {
    var body: some View {
        TabView {
            Tab("Discover", systemImage: "sparkles") {
                DiscoverView()
            }
            Tab("Parties", systemImage: "party.popper") {
                ComingSoon(title: "Parties")
            }
            Tab("Chats", systemImage: "bubble.left.and.bubble.right") {
                ComingSoon(title: "Chats")
            }
            Tab("Me", systemImage: "person.crop.circle") {
                ProfileView()
            }
        }
    }
}

/// Placeholder for tabs that aren't built yet.
struct ComingSoon: View {
    let title: String

    var body: some View {
        NavigationStack {
            ContentUnavailableView(title, systemImage: "hammer", description: Text("Coming next."))
                .navigationTitle(title)
        }
    }
}
