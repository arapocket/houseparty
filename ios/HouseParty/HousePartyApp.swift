import SwiftUI

@main
struct HousePartyApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .task { await model.start() }
                // Always dark: it's a nightlife app.
                .preferredColorScheme(.dark)
                .tint(Theme.pink)
                .fontDesign(.rounded)
        }
    }
}

/// Picks the screen for where you are: signing in, setting up, or in.
struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        switch model.phase {
        case .loading:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity).partyScreen()
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
            Tab("Parties", systemImage: "party.popper.fill") {
                PartiesView()
            }
            Tab("Chats", systemImage: "bubble.left.and.bubble.right.fill") {
                ComingSoon(title: "Chats")
            }
            Tab("Me", systemImage: "person.crop.circle.fill") {
                ProfileView()
            }
        }
    }
}

/// Placeholder for tabs that aren't built yet.
struct ComingSoon: View {
    let title: String

    var body: some View {
        VStack(alignment: .leading) {
            ScreenTitle(text: title)
            Spacer()
            EmptyState(title: "Coming next", message: "This part is being built.", systemImage: "hammer.fill")
            Spacer()
        }
        .padding(20)
        .partyScreen()
    }
}
